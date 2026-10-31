"""Cash paid out as an expense has left the drawer: the shift's expected cash goes down by it."""

import frappe
from frappe.utils import flt

from klik_pos.api import expense
from klik_pos.api.pos_entry import _calculate_payment_reconciliation, closing_summary, expected_by_mode
from klik_pos.tests.pos_fixtures import open_own_shift

TILL = "_Test Expense Close Till"


class TestClosingCountsExpenses(frappe.tests.utils.FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.profile = open_own_shift(cls, TILL)
		if not cls.profile:
			raise cls.skipTest(cls, "no till to copy")
		cls.company = cls.profile.company
		cls.mode = cls.pay_from = None
		for p in cls.profile.payments:
			account = frappe.db.get_value(
				"Mode of Payment Account", {"parent": p.mode_of_payment, "company": cls.company}, "default_account"
			)
			if account:
				cls.mode, cls.pay_from = p.mode_of_payment, account
				break
		if not cls.mode:
			raise cls.skipTest(cls, "no till mode with an account")
		cls.expense_account = frappe.db.get_value(
			"Account", {"company": cls.company, "root_type": "Expense", "is_group": 0}, "name", order_by="name"
		)
		cls.addClassCleanup(frappe.db.rollback)

	def setUp(self):
		frappe.set_user("Administrator")
		self._profile()
		self.shift = expense.get_current_pos_opening_entry()
		self.addCleanup(self._clean_jes)
		self.base = self._expected()

	def _profile(self, **values):
		p = frappe.get_doc("POS Profile", TILL)
		p.custom_expense_account = values.get("account", self.pay_from)
		p.custom_expenses_need_approval = values.get("approval", 0)
		p.set("custom_expense_types", [{"label": "Newspaper", "expense_account": self.expense_account}])
		p.applicable_for_users[0].custom_can_record_expenses = 1
		p.save(ignore_permissions=True)

	def _clean_jes(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Journal Entry", {"custom_pos_profile": TILL}, pluck="name"):
			if frappe.db.get_value("Journal Entry", name, "docstatus") == 1:
				frappe.get_doc("Journal Entry", name).cancel()
			frappe.delete_doc("Journal Entry", name, force=True, ignore_permissions=True)

	def _expected(self):
		return {m: flt(r["expected_amount"]) for m, r in expected_by_mode(self.shift).items()}

	def test_expense_reduces_expected_on_matching_mode(self):
		expense.record_expense("Newspaper", 350)
		row = expected_by_mode(self.shift)[self.mode]
		self.assertEqual(flt(row["expense_amount"]), 350)
		self.assertEqual(flt(row["expected_amount"]), self.base.get(self.mode, 0) - 350)

	def test_draft_expense_counts(self):
		self._profile(approval=1)
		self.assertEqual(expense.record_expense("Newspaper", 350)["docstatus"], 0)
		self.assertEqual(self._expected()[self.mode], self.base.get(self.mode, 0) - 350)

	def test_cancelled_and_deleted_expenses_do_not_count(self):
		submitted = expense.record_expense("Newspaper", 100)["name"]
		self._profile(approval=1)
		draft = expense.record_expense("Newspaper", 200)["name"]
		self.assertEqual(self._expected()[self.mode], self.base.get(self.mode, 0) - 300)
		frappe.get_doc("Journal Entry", submitted).cancel()
		frappe.delete_doc("Journal Entry", draft, force=True, ignore_permissions=True)
		self.assertEqual(self._expected().get(self.mode, 0), self.base.get(self.mode, 0))

	def test_unmatched_pay_from_account_leaves_drawer_alone(self):
		mapped = set(
			frappe.get_all(
				"Mode of Payment Account", {"company": self.company}, pluck="default_account"
			)
		)
		other = frappe.db.get_value(
			"Account",
			{
				"company": self.company,
				"is_group": 0,
				"account_currency": frappe.get_cached_value("Company", self.company, "default_currency"),
				"account_type": ("in", ["Cash", "Bank"]),
				"name": ("not in", list(mapped) or [""]),
			},
			"name",
		)
		if not other:
			self.skipTest("no unmapped Cash/Bank account")
		self._profile(account=other)
		expense.record_expense("Newspaper", 350)
		self.assertEqual(self._expected(), self.base)

	def test_two_users_in_one_shift_both_count(self):
		from klik_pos.api.shift import JOINED_SHIFT_KEY
		from klik_pos.tests.test_opening_conflict import _user

		cashier = _user("expense-close-cashier@example.com")
		profile = frappe.get_doc("POS Profile", TILL)
		profile.append("applicable_for_users", {"user": cashier, "custom_can_record_expenses": 1})
		profile.save(ignore_permissions=True)
		frappe.defaults.set_user_default(JOINED_SHIFT_KEY, self.shift, cashier)
		self.addCleanup(frappe.defaults.clear_user_default, JOINED_SHIFT_KEY, cashier)

		expense.record_expense("Newspaper", 100)
		frappe.set_user(cashier)
		expense.record_expense("Newspaper", 40)
		frappe.set_user("Administrator")
		self.assertEqual(self._expected()[self.mode], self.base.get(self.mode, 0) - 140)
		self.assertEqual({r["owner"] for r in expense.expenses_for_shifts([self.shift])}, {"Administrator", cashier})

	def test_closing_entry_files_reduced_expected(self):
		expense.record_expense("Newspaper", 350)
		filed = _calculate_payment_reconciliation(
			frappe._dict(name=self.shift), {"closing_balance": {self.mode: 0}}
		)
		row = next(r for r in filed if r["mode_of_payment"] == self.mode)
		self.assertEqual(flt(row["expected_amount"]), self.base.get(self.mode, 0) - 350)

	def test_hidden_figures_zero_the_expense(self):
		from unittest.mock import patch

		expense.record_expense("Newspaper", 350)
		with patch("klik_pos.api.payment._hides_expected_amount", return_value=True):
			summary = closing_summary()
		self.assertTrue(summary["figures_hidden"])
		self.assertEqual({flt(m["expense_amount"]) for m in summary["modes"]}, {0})
