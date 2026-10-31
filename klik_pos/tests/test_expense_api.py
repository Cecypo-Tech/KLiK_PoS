"""Recording a till expense as a Journal Entry."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import expense
from klik_pos.tests.pos_fixtures import open_own_shift

TILL = "_Test Expense Till"


class TestExpenseApi(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.profile = open_own_shift(cls, TILL)
		if not cls.profile:
			raise cls.skipTest(cls, "no till to copy")
		cls.company = cls.profile.company
		cls.pay_from = frappe.db.get_value("Company", cls.company, "default_cash_account")
		cls.expense_account = frappe.db.get_value(
			"Account",
			{"company": cls.company, "root_type": "Expense", "is_group": 0},
			"name",
			order_by="name",
		)
		frappe.db.set_value(
			"POS Profile User", {"parent": TILL, "user": "Administrator"}, "custom_can_record_expenses", 1
		)
		cls.addClassCleanup(frappe.db.rollback)

	def setUp(self):
		frappe.set_user("Administrator")
		p = frappe.get_doc("POS Profile", TILL)
		p.custom_expense_account = self.pay_from
		p.custom_expenses_need_approval = 0
		p.set("custom_expense_types", [{"label": "Newspaper", "expense_account": self.expense_account}])
		p.applicable_for_users[0].custom_can_record_expenses = 1
		p.save(ignore_permissions=True)
		self.addCleanup(self._clean_jes)

	def _clean_jes(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Journal Entry", {"custom_pos_profile": TILL}, pluck="name"):
			je = frappe.get_doc("Journal Entry", name)
			if je.docstatus == 1:
				je.cancel()
			frappe.delete_doc("Journal Entry", name, force=True, ignore_permissions=True)

	def _set(self, **values):
		for k, v in values.items():
			frappe.db.set_value("POS Profile", TILL, k, v)
		frappe.clear_document_cache("POS Profile", TILL)

	def test_records_and_submits(self):
		res = expense.record_expense("Newspaper", 350, "Daily Nation")
		je = frappe.get_doc("Journal Entry", res["name"])
		self.assertEqual((je.docstatus, je.voucher_type), (1, "Cash Entry"))
		self.assertEqual(res["docstatus"], 1)
		credit = {a.account: a.credit_in_account_currency for a in je.accounts}
		debit = {a.account: a.debit_in_account_currency for a in je.accounts}
		self.assertEqual(credit[self.pay_from], 350)
		self.assertEqual(debit[self.expense_account], 350)
		self.assertEqual(je.custom_pos_profile, TILL)
		self.assertEqual(je.custom_warehouse, self.profile.warehouse)
		self.assertTrue(je.custom_pos_opening_entry)
		self.assertEqual(je.custom_expense_type, "Newspaper")
		self.assertEqual(je.user_remark, "Newspaper: Daily Nation")

	def test_remark_is_just_the_label_without_a_note(self):
		res = expense.record_expense("Newspaper", 10)
		self.assertEqual(frappe.db.get_value("Journal Entry", res["name"], "user_remark"), "Newspaper")

	def test_draft_when_approval_on(self):
		self._set(custom_expenses_need_approval=1)
		self.assertEqual(expense.record_expense("Newspaper", 50)["docstatus"], 0)

	def test_refuses_unknown_type(self):
		with self.assertRaises(frappe.ValidationError):
			expense.record_expense("Rent", 100)

	def test_refuses_non_positive_amount(self):
		for bad in (0, -5, "abc"):
			with self.assertRaises(frappe.ValidationError):
				expense.record_expense("Newspaper", bad)

	def test_refuses_user_without_tick(self):
		frappe.db.set_value("POS Profile User", {"parent": TILL}, "custom_can_record_expenses", 0)
		frappe.clear_document_cache("POS Profile", TILL)
		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaises(frappe.PermissionError):
				expense.record_expense("Newspaper", 10)

	def test_refuses_without_open_shift(self):
		with patch("klik_pos.api.expense.get_current_pos_opening_entry", return_value=None):
			with self.assertRaisesRegex(frappe.ValidationError, "No open shift"):
				expense.record_expense("Newspaper", 10)

	def test_no_pay_from_account_means_off(self):
		self._set(custom_expense_account=None)
		self.assertIs(expense.may_record_expenses(TILL, "Administrator"), False)
		self.assertEqual(expense.expense_types(), [])

	def test_types_return_labels_only(self):
		self.assertEqual(expense.expense_types(), [{"label": "Newspaper"}])

	def test_refuses_a_type_account_that_is_a_group(self):
		group = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Expense", "is_group": 1}, "name"
		)
		frappe.db.set_value("POS Profile Expense Type", {"parent": TILL}, "expense_account", group)
		with self.assertRaisesRegex(frappe.ValidationError, "expense account"):
			expense.record_expense("Newspaper", 10)

	def test_refuses_a_pay_from_account_that_is_not_cash_or_bank(self):
		self._set(custom_expense_account=self.expense_account)
		with self.assertRaisesRegex(frappe.ValidationError, "Pay expenses from"):
			expense.record_expense("Newspaper", 10)

	def test_shift_expenses_lists_the_shift(self):
		res = expense.record_expense("Newspaper", 20, "x")
		rows = expense.shift_expenses()
		self.assertEqual([r["name"] for r in rows], [res["name"]])
		self.assertEqual((rows[0]["label"], rows[0]["note"], rows[0]["amount"]), ("Newspaper", "x", 20))

	def test_user_info_exposes_the_flag(self):
		from klik_pos.api.user import get_current_user_info

		with patch(
			"klik_pos.klik_pos.utils.get_current_pos_profile",
			return_value=frappe.get_doc("POS Profile", TILL),
		):
			self.assertTrue(get_current_user_info()["data"]["can_record_expenses"])
