"""A till opens where it last closed, and only cash carries a float.

ERPNext carries nothing from one shift to the next: the opening screen offered zero for
every mode and whatever the cashier typed became the figure the shift was judged against.
Understating it is the edit that hides a shortfall - the count at close still reconciles,
and the missing money is never asked about - so a change now needs a reason next to it.

Non-cash modes hold no float at all. Card, transfer and M-Pesa money goes to its account,
never the drawer, and the balance of that account is not a cashier's business.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.opening_balances import carries_float, enforce, enforce_banking, last_closing, opening_suggestion
from klik_pos.api.pos_entry import _parse_request_data

COMPANY = "Dev Co"
CASH = "Cash"
PHONE = "Mpesa-111222"
BANK = "Cheque"


def _profile_with_modes(name, modes):
	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": name,
			"company": COMPANY,
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
			"warehouse": frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name"),
			"payments": [{"mode_of_payment": m, "default": 1 if i == 0 else 0} for i, m in enumerate(modes)],
		}
	)
	profile.flags.ignore_mandatory = True
	profile.insert(ignore_permissions=True, ignore_mandatory=True)
	return profile.name


def _file_closing(profile, counted, banked=None):
	"""A submitted POS Closing Entry counting `counted` per mode, with `banked` handed over
	for banking, without driving the whole close: what is under test reads the filed
	figures, not how they got there."""
	banked = banked or {}
	closing = frappe.get_doc(
		{
			"doctype": "POS Closing Entry",
			"pos_profile": profile,
			"company": COMPANY,
			"user": frappe.session.user,
			"period_start_date": frappe.utils.add_to_date(None, hours=-8),
			"period_end_date": frappe.utils.add_to_date(None, hours=-1),
			"posting_date": frappe.utils.nowdate(),
			"payment_reconciliation": [
				{
					"mode_of_payment": mode,
					"opening_amount": 0,
					"expected_amount": amount,
					"closing_amount": amount,
					"custom_banked_amount": banked.get(mode, 0),
				}
				for mode, amount in counted.items()
			],
		}
	)
	closing.flags.ignore_validate = True
	closing.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value("POS Closing Entry", closing.name, "docstatus", 1, update_modified=False)
	return closing.name


class OpeningCase(FrappeTestCase):
	def _opening(self, profile, rows):
		doc = frappe.new_doc("POS Opening Entry")
		doc.update(
			{
				"pos_profile": profile,
				"company": COMPANY,
				"user": frappe.session.user,
				"period_start_date": frappe.utils.now_datetime(),
				"posting_date": frappe.utils.nowdate(),
			}
		)
		for row in rows:
			doc.append("balance_details", row)
		return doc


class TestWhichModesCarryAFloat(OpeningCase):
	def test_cash_carries_a_float(self):
		self.assertTrue(carries_float(CASH))

	def test_a_phone_mode_does_not(self):
		self.assertFalse(carries_float(PHONE), "M-Pesa money never reaches the drawer")

	def test_a_bank_mode_does_not(self):
		self.assertFalse(carries_float(BANK))


class TestTheSuggestion(OpeningCase):
	def test_a_cash_mode_is_suggested_at_what_the_till_last_counted(self):
		profile = _profile_with_modes(f"OB Suggest {frappe.generate_hash(length=5)}", [CASH, PHONE])
		_file_closing(profile, {CASH: 3000, PHONE: 12500})

		modes = {m["mode_of_payment"]: m for m in opening_suggestion(profile)["modes"]}

		self.assertEqual(flt(modes[CASH]["suggested_amount"]), 3000.0)
		self.assertTrue(modes[CASH]["carries_float"])
		self.assertTrue(modes[CASH]["previous_closing_entry"])

	def test_a_phone_mode_is_suggested_at_zero_however_much_it_took(self):
		profile = _profile_with_modes(f"OB Phone {frappe.generate_hash(length=5)}", [CASH, PHONE])
		_file_closing(profile, {CASH: 3000, PHONE: 12500})

		modes = {m["mode_of_payment"]: m for m in opening_suggestion(profile)["modes"]}

		self.assertEqual(flt(modes[PHONE]["suggested_amount"]), 0.0)
		self.assertFalse(modes[PHONE]["carries_float"])
		self.assertIsNone(modes[PHONE]["previous_closing_entry"], "and its account is not named")

	def test_a_till_that_has_never_closed_suggests_nothing(self):
		profile = _profile_with_modes(f"OB Fresh {frappe.generate_hash(length=5)}", [CASH])

		modes = {m["mode_of_payment"]: m for m in opening_suggestion(profile)["modes"]}

		self.assertEqual(flt(modes[CASH]["suggested_amount"]), 0.0)
		self.assertEqual(last_closing(profile), {})


class TestWhatTheTillWillAccept(OpeningCase):
	def test_a_float_on_a_phone_mode_is_refused(self):
		profile = _profile_with_modes(f"OB Refuse {frappe.generate_hash(length=5)}", [CASH, PHONE])
		doc = self._opening(profile, [{"mode_of_payment": PHONE, "opening_amount": 500}])

		with self.assertRaises(frappe.ValidationError) as caught:
			enforce(doc)

		self.assertIn(PHONE, str(caught.exception))

	def test_a_phone_mode_at_zero_passes(self):
		profile = _profile_with_modes(f"OB Zero {frappe.generate_hash(length=5)}", [CASH, PHONE])
		doc = self._opening(profile, [{"mode_of_payment": PHONE, "opening_amount": 0}])

		enforce(doc)  # no throw

	def test_opening_cash_where_it_closed_passes_and_records_the_figure(self):
		profile = _profile_with_modes(f"OB Same {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 3000})
		doc = self._opening(profile, [{"mode_of_payment": CASH, "opening_amount": 3000}])

		enforce(doc)

		self.assertEqual(flt(doc.balance_details[0].get("custom_previous_closing_amount")), 3000.0)

	def test_opening_cash_short_of_the_last_closing_needs_a_reason(self):
		"""3,000 counted last night, 2,500 declared this morning: the 500 has to be spoken
		for, or the shortfall reconciles away silently at close."""
		profile = _profile_with_modes(f"OB Short {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 3000})
		doc = self._opening(profile, [{"mode_of_payment": CASH, "opening_amount": 2500}])

		with self.assertRaises(frappe.ValidationError) as caught:
			enforce(doc)

		self.assertIn("3000", str(caught.exception).replace(",", ""))

	def test_a_reason_lets_the_difference_through_and_is_kept(self):
		profile = _profile_with_modes(f"OB Reason {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 3000})
		doc = self._opening(
			profile,
			[
				{
					"mode_of_payment": CASH,
					"opening_amount": 2500,
					"custom_variance_reason": "500 banked overnight, slip 4471",
				}
			],
		)

		enforce(doc)

		row = doc.balance_details[0]
		self.assertEqual(row.get("custom_variance_reason"), "500 banked overnight, slip 4471")
		self.assertEqual(flt(row.get("custom_previous_closing_amount")), 3000.0)

	def test_blank_space_is_not_a_reason(self):
		profile = _profile_with_modes(f"OB Blank {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 3000})
		doc = self._opening(
			profile, [{"mode_of_payment": CASH, "opening_amount": 2500, "custom_variance_reason": "   "}]
		)

		with self.assertRaises(frappe.ValidationError):
			enforce(doc)

	def test_a_till_with_no_history_takes_any_opening_without_explanation(self):
		profile = _profile_with_modes(f"OB First {frappe.generate_hash(length=5)}", [CASH])
		doc = self._opening(profile, [{"mode_of_payment": CASH, "opening_amount": 1500}])

		enforce(doc)  # no throw

	def test_the_rule_holds_on_a_document_saved_anywhere(self):
		"""The desk creates opening entries too, so the guard hangs off validate rather
		than off the till's own endpoint."""
		profile = _profile_with_modes(f"OB Hook {frappe.generate_hash(length=5)}", [CASH, PHONE])
		_file_closing(profile, {CASH: 3000})
		doc = self._opening(profile, [{"mode_of_payment": PHONE, "opening_amount": 250}])

		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)


class TestBankingAtClosing(OpeningCase):
	"""A closing counts 100,000 and most of it goes to the bank. The next opening must offer
	the float left behind, not the whole count, or every morning opens on a 'difference'."""

	def test_the_next_opening_suggests_what_was_left_after_banking(self):
		profile = _profile_with_modes(f"OB Bank {frappe.generate_hash(length=5)}", [CASH, PHONE])
		_file_closing(profile, {CASH: 100000, PHONE: 40000}, banked={CASH: 95000})

		modes = {m["mode_of_payment"]: m for m in opening_suggestion(profile)["modes"]}

		self.assertEqual(flt(modes[CASH]["suggested_amount"]), 5000.0)
		self.assertEqual(flt(modes[CASH]["previous_counted_amount"]), 100000.0)
		self.assertEqual(flt(modes[CASH]["previous_banked_amount"]), 95000.0)
		self.assertEqual(flt(modes[PHONE]["suggested_amount"]), 0.0)

	def test_opening_at_the_float_left_needs_no_reason(self):
		profile = _profile_with_modes(f"OB BankOpen {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 100000}, banked={CASH: 95000})
		doc = self._opening(profile, [{"mode_of_payment": CASH, "opening_amount": 5000}])

		enforce(doc)  # no throw

	def test_opening_at_the_full_count_after_banking_needs_a_reason(self):
		profile = _profile_with_modes(f"OB BankFull {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 100000}, banked={CASH: 95000})
		doc = self._opening(profile, [{"mode_of_payment": CASH, "opening_amount": 100000}])

		with self.assertRaises(frappe.ValidationError):
			enforce(doc)

	def test_a_closing_with_nothing_banked_suggests_the_full_count(self):
		profile = _profile_with_modes(f"OB NoBank {frappe.generate_hash(length=5)}", [CASH])
		_file_closing(profile, {CASH: 3000})

		modes = {m["mode_of_payment"]: m for m in opening_suggestion(profile)["modes"]}

		self.assertEqual(flt(modes[CASH]["suggested_amount"]), 3000.0)

	def _closing_doc(self, mode, counted, banked):
		doc = frappe.new_doc("POS Closing Entry")
		doc.append(
			"payment_reconciliation",
			{
				"mode_of_payment": mode,
				"closing_amount": counted,
				"expected_amount": counted,
				"custom_banked_amount": banked,
			},
		)
		return doc

	def test_banking_more_than_counted_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			enforce_banking(self._closing_doc(CASH, 100000, 150000))
		self.assertIn(CASH, str(caught.exception))

	def test_banking_on_a_mode_without_a_float_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			enforce_banking(self._closing_doc(PHONE, 40000, 40000))
		self.assertIn(PHONE, str(caught.exception))

	def test_negative_banking_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			enforce_banking(self._closing_doc(CASH, 1000, -5))

	def test_banking_all_of_it_is_allowed(self):
		enforce_banking(self._closing_doc(CASH, 100000, 100000))  # no throw


class TestClosingRequestCarriesBanking(FrappeTestCase):
	def test_banked_amounts_are_read_per_mode(self):
		frappe.local.form_dict = frappe._dict(
			{
				"closing_balance": [
					{"mode_of_payment": CASH, "closing_amount": 100000, "banked_amount": 95000},
					{"mode_of_payment": PHONE, "closing_amount": 40000},
				]
			}
		)
		data = _parse_request_data()
		self.assertEqual(data["closing_balance"], {CASH: 100000, PHONE: 40000})
		self.assertEqual(data["banked_balance"], {CASH: 95000})
