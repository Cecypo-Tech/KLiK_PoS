"""One shift per till, joined by every cashier on it.

Each cashier used to open their own POS Opening Entry, even on a shared till, and the close
then counted the whole till's sales for each of them. A till now runs one shift: the first
cashier opens it, the others join it, and whoever closes it closes it for everyone.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import shift
from klik_pos.api.pos_entry import open_pos, opening_conflict
from klik_pos.api.sales_invoice import get_current_pos_opening_entry
from klik_pos.tests.test_opening_conflict import COMPANY, _profile, _shift, _user

OPENER = "shared-shift-opener@example.com"
JOINER = "shared-shift-joiner@example.com"


def _assign(profile, *users):
	doc = frappe.get_doc("POS Profile", profile)
	for user in users:
		doc.append("applicable_for_users", {"user": user})
	# The fixture profile was inserted with ignore_mandatory; saving it must skip the same checks.
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


class SharedShiftCase(FrappeTestCase):
	def setUp(self):
		_user(OPENER)
		_user(JOINER)
		self.till = _profile()
		_assign(self.till, OPENER, JOINER)
		frappe.defaults.clear_user_default(shift.JOINED_SHIFT_KEY, JOINER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestJoining(SharedShiftCase):
	def test_a_cashier_on_the_till_joins_its_open_shift(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		self.assertEqual(shift.join_shift(self.till), {"success": True, "entry": entry})
		self.assertEqual(get_current_pos_opening_entry(), entry)
		self.assertTrue(open_pos())

	def test_a_cashier_not_on_the_till_cannot_join(self):
		_shift(self.till, OPENER)
		outsider = _user("shared-shift-outsider@example.com")
		frappe.set_user(outsider)

		with self.assertRaises(frappe.PermissionError):
			shift.join_shift(self.till)

	def test_there_is_nothing_to_join_on_a_closed_till(self):
		frappe.set_user(JOINER)
		with self.assertRaises(frappe.ValidationError):
			shift.join_shift(self.till)

	def test_a_joined_shift_that_has_closed_is_forgotten(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		frappe.db.set_value("POS Opening Entry", entry, "status", "Closed")

		self.assertIsNone(get_current_pos_opening_entry())
		self.assertFalse(open_pos())

	def test_my_own_open_shift_wins_over_a_joined_one(self):
		other_till = _profile()
		_assign(other_till, JOINER)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		mine = _shift(other_till, JOINER)

		self.assertEqual(get_current_pos_opening_entry(), mine)


class TestOneShiftPerTill(SharedShiftCase):
	def test_another_cashier_s_shift_today_is_offered_to_join(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_open")
		self.assertEqual(conflict["entry"], entry)
		self.assertEqual(conflict["user"], OPENER)

	def test_another_cashier_s_shift_from_yesterday_is_offered_to_join_and_close(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		self.assertEqual(opening_conflict(self.till)["kind"], "till_stale")

	def test_a_joined_shift_on_this_till_is_continued(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		conflict = opening_conflict(self.till)
		self.assertEqual((conflict["kind"], conflict["entry"]), ("own_open", entry))

	def test_erpnext_refuses_a_second_shift_on_a_till(self):
		"""klik no longer switches ERPNext's own check off."""
		_shift(self.till, OPENER)
		doc = frappe.new_doc("POS Opening Entry")
		doc.update({"pos_profile": self.till, "user": JOINER, "company": COMPANY})

		with self.assertRaises(frappe.ValidationError):
			doc.check_open_pos_exists()

	def _invoice(self, **overrides):
		"""A klik POS invoice doc, in memory, not inserted."""
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": COMPANY,
				"customer": "Walk In",
				"pos_profile": self.till,
				"is_pos": 1,
				"custom_is_created_from_klik": 1,
			}
		)
		doc.update(overrides)
		return doc

	def _before_submit(self, doc):
		"""Call before_submit with the rest of its body stubbed out, so only the
		shift check under test can raise."""
		with (
			patch.object(type(doc), "validate_reserved_stock_availability"),
			patch.object(type(doc), "validate_full_payment"),
			patch("klik_pos.api.sales_invoice._should_reserve_stock", return_value=False),
		):
			doc.before_submit()

	def test_sales_invoices_use_erpnext_s_own_shift_check(self):
		"""klik must not reimplement ERPNext's shift rule."""
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

		from klik_pos.api.sales_invoice import CustomSalesInvoice

		self.assertIs(CustomSalesInvoice.validate_pos_opening_entry, SalesInvoice.validate_pos_opening_entry)

	def test_before_submit_refuses_a_klik_sale_with_no_open_shift(self):
		frappe.set_user(OPENER)
		doc = self._invoice()

		with self.assertRaises(frappe.ValidationError):
			self._before_submit(doc)

	def test_before_submit_refuses_a_klik_sale_on_a_stale_shift(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		doc = self._invoice()

		with self.assertRaises(frappe.ValidationError):
			self._before_submit(doc)

	def test_before_submit_allows_a_klik_sale_on_today_s_shift(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)
		doc = self._invoice()

		self._before_submit(doc)

	def test_before_submit_ignores_the_shift_on_a_return(self):
		frappe.set_user(OPENER)
		doc = self._invoice(is_return=1)

		self._before_submit(doc)

	def test_before_submit_ignores_the_shift_when_not_a_pos_sale(self):
		frappe.set_user(OPENER)
		doc = self._invoice(is_pos=0)

		self._before_submit(doc)

	def test_before_submit_skips_the_check_for_a_queued_worker(self):
		frappe.set_user(OPENER)
		doc = self._invoice()

		frappe.flags.klik_processing_queued_invoice = True
		try:
			self._before_submit(doc)
		finally:
			frappe.flags.klik_processing_queued_invoice = False


from klik_pos.api.pos_entry import _calculate_payment_reconciliation, _get_open_pos_entry


def _paid_invoice(till, entry, owner, amount):
	"""A submitted cash sale stamped with `entry`, written past validation."""
	si = frappe.new_doc("Sales Invoice")
	si.update({"company": COMPANY, "customer": "Walk In", "pos_profile": till,
		"posting_date": frappe.utils.nowdate(), "custom_pos_opening_entry": entry})
	si.append("items", {"item_code": "Consulting", "qty": 1, "rate": amount})
	si.flags.ignore_validate = True
	si.flags.ignore_mandatory = True
	si.insert(ignore_permissions=True)
	si.append("payments", {"mode_of_payment": "Cash", "amount": amount})
	si.db_update_all()
	frappe.db.set_value("Sales Invoice", si.name, {"docstatus": 1, "owner": owner}, update_modified=False)
	frappe.db.sql(
		"update `tabSales Invoice Payment` set docstatus=1, amount=%s where parent=%s", (amount, si.name)
	)
	return si.name


class TestClosingTheTill(SharedShiftCase):
	def test_a_joined_cashier_closes_the_till_s_shift(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		self.assertEqual(_get_open_pos_entry(JOINER).name, entry)

	def test_the_close_counts_every_cashier_s_sales_once(self):
		entry = _shift(self.till, OPENER)
		_paid_invoice(self.till, entry, OPENER, 100)
		_paid_invoice(self.till, entry, JOINER, 50)
		# A sale on the same till under an older, different (now closed) shift must not be
		# counted: a real POS Opening Entry, not just a name, so the invoice's link validates.
		older = _shift(self.till, OPENER, status="Closed", days_ago=2)
		_paid_invoice(self.till, older, OPENER, 999)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		opening = _get_open_pos_entry(JOINER)

		rows = _calculate_payment_reconciliation(opening, {"closing_balance": {"Cash": 150}})
		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")

		self.assertEqual(frappe.utils.flt(cash["expected_amount"]), 150)
