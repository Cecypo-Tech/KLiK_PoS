"""A shift's totals must count each invoice once, not once per line.

`_calculate_closing_entry_totals` LEFT JOINed `Sales Invoice Item` and then summed the
parent's `net_total` and `grand_total`, so every sum was multiplied by that invoice's
line count. A three-line invoice was counted three times. On dev, opening entry
POS-OPE-2026-00013 reported 1,466.24 over six invoices that really totalled 1,346.76 --
and the inflated figure is what the closing entry stores, what the cashier reconciles
cash against, and what the new dashboard is validated against.

Quantity now comes from the parent's own `total_qty` rather than from the item rows,
which is the number those rows would have summed to.

The invoices are linked to the opening entry by writing the column directly: the function
is a single SQL statement keyed on `custom_pos_opening_entry`, so a real POS Opening Entry
(which needs a profile, a user and balance details) would add setup without adding
coverage. The token is unique per run so a parallel or repeated run cannot collide.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.pos_entry import _calculate_closing_entry_totals

COMPANY = "Dev Co"
ITEM = "Consulting"


def _make_customer(name):
	if frappe.db.exists("Customer", name):
		return name
	doc = frappe.get_doc(
		{"doctype": "Customer", "customer_name": name, "customer_type": "Individual"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_invoice(customer, lines, opening_entry):
	"""A submitted invoice with `lines` item rows, attached to `opening_entry`."""
	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.company = COMPANY
	si.is_pos = 0
	for qty, rate in lines:
		si.append("items", {"item_code": ITEM, "qty": qty, "rate": rate})
	si.insert(ignore_permissions=True)
	si.submit()
	frappe.db.set_value(
		"Sales Invoice", si.name, "custom_pos_opening_entry", opening_entry, update_modified=False
	)
	return si


class TestClosingEntryTotals(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=8)
		cls.opening_entry = f"TEST-OPE-{suffix}"
		cls.customer = _make_customer(f"CET Test Customer {suffix}")

		# Three lines and two lines: line counts differ, so a fanout cannot be mistaken
		# for a constant multiplier that a single-invoice test would miss.
		cls.three_line = _make_invoice(cls.customer, [(1, 100), (2, 50), (3, 10)], cls.opening_entry)
		cls.two_line = _make_invoice(cls.customer, [(1, 200), (4, 25)], cls.opening_entry)

		# Same shape, no opening entry: proves the filter still selects.
		cls.unlinked = _make_invoice(cls.customer, [(1, 999)], "")

		cls.totals = _calculate_closing_entry_totals(cls.opening_entry)

	def test_grand_total_counts_each_invoice_once(self):
		"""The regression. Before the fix this was 3x the first invoice plus 2x the second."""
		expected = flt(self.three_line.grand_total) + flt(self.two_line.grand_total)

		self.assertAlmostEqual(self.totals["grand_total"], expected, places=2)

	def test_net_total_counts_each_invoice_once(self):
		expected = flt(self.three_line.net_total) + flt(self.two_line.net_total)

		self.assertAlmostEqual(self.totals["net_total"], expected, places=2)

	def test_quantity_is_the_sum_of_the_lines(self):
		"""total_qty must still be the item quantity, not an invoice count."""
		self.assertAlmostEqual(self.totals["total_quantity"], 1 + 2 + 3 + 1 + 4, places=2)

	def test_the_inflated_figure_is_actually_different(self):
		"""Pins that the fixtures can tell the two queries apart.

		Multi-line invoices are what make the fanout visible; if a future edit reduced these
		fixtures to one line each, every assertion above would still pass while proving
		nothing. This computes what the old joined query would have returned and requires it
		to disagree.
		"""
		inflated = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(si.grand_total), 0)
			FROM `tabSales Invoice` si
			LEFT JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
			WHERE si.custom_pos_opening_entry = %s AND si.docstatus = 1
			""",
			(self.opening_entry,),
		)[0][0]

		self.assertGreater(flt(inflated), self.totals["grand_total"])

	def test_invoices_of_another_shift_are_not_counted(self):
		self.assertNotIn(flt(self.unlinked.grand_total), [self.totals["grand_total"]])
		self.assertAlmostEqual(
			self.totals["grand_total"],
			flt(self.three_line.grand_total) + flt(self.two_line.grand_total),
			places=2,
		)

	def test_a_shift_with_no_invoices_is_zero_not_an_error(self):
		totals = _calculate_closing_entry_totals(f"TEST-OPE-EMPTY-{frappe.generate_hash(length=6)}")

		self.assertEqual(totals, {"total_quantity": 0.0, "net_total": 0.0, "grand_total": 0.0})


class TestClosingExpectsPaymentEntries(FrappeTestCase):
	def test_a_shift_stamped_payment_entry_counts_toward_expected(self):
		"""M-Pesa money is on Payment Entries now, and the closing entry compared the
		drawer against payment rows alone - which would have said the till took none."""
		from klik_pos.api.pos_entry import _calculate_payment_reconciliation

		opening = frappe.new_doc("POS Opening Entry")
		opening.update({"pos_profile": "_Test POS Profile", "company": "Dev Co", "user": frappe.session.user,
			"period_start_date": frappe.utils.add_to_date(None, hours=-1), "posting_date": frappe.utils.nowdate()})
		opening.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
		opening.flags.ignore_validate = True
		opening.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_value("POS Opening Entry", opening.name, {"docstatus": 1, "status": "Open"}, update_modified=False)
		opening.reload()

		receivable, bank = frappe.db.get_value("Company", "Dev Co", ["default_receivable_account", "default_cash_account"])
		pe = frappe.get_doc({"doctype": "Payment Entry", "payment_type": "Receive", "party_type": "Customer", "party": "Walk In",
			"company": "Dev Co", "posting_date": frappe.utils.nowdate(), "mode_of_payment": "Cash", "paid_from": receivable,
			"paid_to": bank, "paid_amount": 300, "received_amount": 300, "source_exchange_rate": 1, "target_exchange_rate": 1,
			"paid_from_account_currency": "KES", "paid_to_account_currency": "KES", "custom_pos_opening_entry": opening.name})
		pe.insert(ignore_permissions=True)
		pe.submit()

		rows = _calculate_payment_reconciliation(opening, {"closing_balance": {"Cash": 300}})

		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")
		self.assertEqual(flt(cash["expected_amount"]), 300.0)
		self.assertEqual(flt(cash["difference"]), 0.0)

	def test_an_invoice_payment_row_and_a_payment_entry_in_the_same_mode_add_up(self):
		"""Replacement would pass the first test; only a sum passes this one."""
		from klik_pos.api.pos_entry import _calculate_payment_reconciliation

		opening = frappe.new_doc("POS Opening Entry")
		opening.update({"pos_profile": "_Test POS Profile", "company": "Dev Co", "user": frappe.session.user,
			"period_start_date": frappe.utils.add_to_date(None, hours=-1), "posting_date": frappe.utils.nowdate()})
		opening.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
		opening.flags.ignore_validate = True
		opening.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_value("POS Opening Entry", opening.name, {"docstatus": 1, "status": "Open"}, update_modified=False)
		opening.reload()

		# A sale paid at the till: 100 on the profile's Cash row.
		si = frappe.new_doc("Sales Invoice")
		si.update({"customer": "Walk In", "company": "Dev Co", "is_pos": 1, "pos_profile": "_Test POS Profile"})
		si.append("items", {"item_code": "Consulting", "qty": 1, "rate": 100})
		si.set_missing_values()
		si.calculate_taxes_and_totals()
		for row in si.payments:
			row.amount = 0
		si.payments[0].amount = flt(si.rounded_total) or flt(si.grand_total)
		cash_mode = si.payments[0].mode_of_payment
		si.insert(ignore_permissions=True)
		si.submit()
		frappe.db.set_value("Sales Invoice", si.name, "custom_pos_opening_entry", opening.name, update_modified=False)

		receivable, bank = frappe.db.get_value("Company", "Dev Co", ["default_receivable_account", "default_cash_account"])
		pe = frappe.get_doc({"doctype": "Payment Entry", "payment_type": "Receive", "party_type": "Customer", "party": "Walk In",
			"company": "Dev Co", "posting_date": frappe.utils.nowdate(), "mode_of_payment": cash_mode, "paid_from": receivable,
			"paid_to": bank, "paid_amount": 300, "received_amount": 300, "source_exchange_rate": 1, "target_exchange_rate": 1,
			"paid_from_account_currency": "KES", "paid_to_account_currency": "KES", "custom_pos_opening_entry": opening.name})
		pe.insert(ignore_permissions=True)
		pe.submit()

		rows = _calculate_payment_reconciliation(opening, {"closing_balance": {cash_mode: 0}})

		mode_row = next(r for r in rows if r["mode_of_payment"] == cash_mode)
		self.assertEqual(flt(mode_row["expected_amount"]), flt(si.payments[0].amount) + 300.0)


class TestDeskClosingFormSeesPaymentEntries(FrappeTestCase):
	"""The standard POS Closing Entry form asked ERPNext for the shift's payments, and
	ERPNext sums `Sales Invoice Payment` alone - so M-Pesa, which reaches the till as a
	Payment Entry and leaves no payment row behind, came back as 0 and the cashier was
	shown a shortfall the size of the day's takings. Klik's own closing page always
	merged those entries; `klik_pos.overrides.pos_closing_entry.get_invoices` is what
	puts the same figure in front of the desk.

	Every figure here is measured as a change across one call, because the window a
	closing covers is `_Test POS Profile` for the current user and the rest of the suite
	leaves its own shifts inside it. What the override adds is the assertion; what the
	site already held is not.
	"""

	PROFILE = "_Test POS Profile"

	def _shift(self, hours_ago=1, closing_entry=None):
		opening = frappe.new_doc("POS Opening Entry")
		opening.update(
			{
				"pos_profile": self.PROFILE,
				"company": COMPANY,
				"user": frappe.session.user,
				"period_start_date": frappe.utils.add_to_date(None, hours=-hours_ago),
				"posting_date": frappe.utils.nowdate(),
			}
		)
		opening.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
		opening.flags.ignore_validate = True
		opening.insert(ignore_permissions=True, ignore_mandatory=True)
		values = {"docstatus": 1, "status": "Open"}
		if closing_entry:
			# What closing actually leaves behind: a status and a link. period_end_date
			# stays empty, which is why nothing here may read it.
			values["status"] = "Closed"
			values["pos_closing_entry"] = closing_entry
		frappe.db.set_value("POS Opening Entry", opening.name, values, update_modified=False)
		opening.reload()
		return opening

	def _receive(self, shift, amount, mode="Cash"):
		receivable, bank = frappe.db.get_value(
			"Company", COMPANY, ["default_receivable_account", "default_cash_account"]
		)
		pe = frappe.get_doc(
			{
				"doctype": "Payment Entry", "payment_type": "Receive", "party_type": "Customer",
				"party": "Walk In", "company": COMPANY, "posting_date": frappe.utils.nowdate(),
				"mode_of_payment": mode, "paid_from": receivable, "paid_to": bank,
				"paid_amount": amount, "received_amount": amount, "source_exchange_rate": 1,
				"target_exchange_rate": 1, "paid_from_account_currency": "KES",
				"paid_to_account_currency": "KES", "custom_pos_opening_entry": shift.name,
			}
		)
		pe.insert(ignore_permissions=True)
		pe.submit()
		return pe

	def _desk_total(self, shift, mode):
		"""What the form would show for `mode` when closing `shift`."""
		from klik_pos.overrides.pos_closing_entry import get_invoices

		payments = get_invoices(
			start=shift.period_start_date,
			end=frappe.utils.now_datetime(),
			pos_profile=self.PROFILE,
			user=frappe.session.user,
		)["payments"]
		self.assertLessEqual(
			len([p for p in payments if p.get("mode_of_payment") == mode]), 1, "one row per mode"
		)
		return sum(flt(p.get("amount")) for p in payments if p.get("mode_of_payment") == mode)

	def test_a_shift_stamped_payment_entry_reaches_the_form(self):
		shift = self._shift()
		before = self._desk_total(shift, "Cash")

		self._receive(shift, 300)

		self.assertEqual(self._desk_total(shift, "Cash") - before, 300.0)

	def test_it_adds_to_the_till_row_rather_than_replacing_it(self):
		"""Replacement would pass the test above; only a sum passes this one."""
		shift = self._shift()

		si = frappe.new_doc("Sales Invoice")
		si.update({"customer": "Walk In", "company": COMPANY, "is_pos": 1, "pos_profile": self.PROFILE})
		si.append("items", {"item_code": ITEM, "qty": 1, "rate": 100})
		si.set_missing_values()
		si.calculate_taxes_and_totals()
		for row in si.payments:
			row.amount = 0
		si.payments[0].amount = flt(si.rounded_total) or flt(si.grand_total)
		mode = si.payments[0].mode_of_payment
		before = self._desk_total(shift, mode)
		si.insert(ignore_permissions=True)
		si.submit()
		# The flag the desk form filters on, written directly the way this module writes
		# custom_pos_opening_entry: setting it before insert asks the site's POS Settings
		# for permission, and what is under test is the query, not that validation.
		frappe.db.set_value("Sales Invoice", si.name, "is_created_using_pos", 1, update_modified=False)

		till_only = self._desk_total(shift, mode)
		self.assertEqual(till_only - before, flt(si.payments[0].amount), "ERPNext still counts the till")

		self._receive(shift, 300, mode=mode)

		self.assertEqual(self._desk_total(shift, mode) - till_only, 300.0, "and the entry is added to it")

	def test_a_shift_that_began_before_this_one_is_left_out(self):
		"""Money banked under an earlier shift belongs to that shift's closing. Nothing
		may test this by asking when the earlier shift ended: closing leaves
		period_end_date empty, so every past shift looks open."""
		current = self._shift(hours_ago=1)
		before = self._desk_total(current, "Cash")
		earlier = self._shift(hours_ago=6)

		self._receive(earlier, 500)

		self.assertEqual(self._desk_total(current, "Cash"), before, "the earlier shift stays out")

	def test_a_shift_already_reconciled_is_left_out(self):
		"""Counting a shift that has a closing entry would bank its receipts twice."""
		current = self._shift(hours_ago=1)
		before = self._desk_total(current, "Cash")
		reconciled = self._shift(hours_ago=1, closing_entry="POS-CLO-TEST-DESK")

		self._receive(reconciled, 700)

		self.assertEqual(self._desk_total(current, "Cash"), before, "the filed shift stays out")

	def test_the_desk_form_is_actually_wired_to_this_wrapper(self):
		"""The fix is a hook. Without the entry the form calls ERPNext directly and none
		of the tests above describe what a cashier sees."""
		overrides = frappe.get_hooks("override_whitelisted_methods", {})

		self.assertIn(
			"klik_pos.overrides.pos_closing_entry.get_invoices",
			overrides.get("erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry.get_invoices", []),
		)
