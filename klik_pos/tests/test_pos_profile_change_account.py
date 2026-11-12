"""A till's change account must be the account its cash goes into.

With POS Settings "post change GL entries" off, ERPNext takes change only off the payment
row whose account equals account_for_change_amount; any other account and the change is
silently left as customer credit (KRUNAL: Tawa cash posted to Cash-Tawa, change account
Cash-Masii - 56 sales, 16,480 of change never left the books). Saving such a till warns.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.overrides.pos_profile import change_account_mismatches


class TestPOSProfileChangeAccount(FrappeTestCase):
	def setUp(self):
		row = frappe.db.sql(
			"""SELECT mpa.parent AS mode, mpa.company, mpa.default_account AS account
			FROM `tabMode of Payment Account` mpa
			JOIN `tabMode of Payment` mop ON mop.name = mpa.parent
			WHERE mop.type = 'Cash' AND IFNULL(mpa.default_account, '') != ''
			LIMIT 1""",
			as_dict=True,
		)
		if not row:
			self.skipTest("no Cash mode of payment with an account on this site")
		self.mode, self.company, self.cash_account = row[0].mode, row[0].company, row[0].account
		self.other_account = frappe.db.get_value(
			"Account",
			{"company": self.company, "is_group": 0, "name": ["!=", self.cash_account]},
			"name",
		)

	def _till(self, change_account):
		doc = frappe.new_doc("POS Profile")
		doc.company = self.company
		doc.account_for_change_amount = change_account
		doc.append("payments", {"mode_of_payment": self.mode})
		return doc

	def test_a_change_account_matching_the_cash_account_is_fine(self):
		self.assertEqual(change_account_mismatches(self._till(self.cash_account)), [])

	def test_a_change_account_other_than_the_cash_account_is_reported(self):
		self.assertEqual(
			change_account_mismatches(self._till(self.other_account)),
			[(self.mode, self.cash_account)],
		)

	def test_a_blank_change_account_falls_back_to_the_company_cash_account(self):
		default_cash = frappe.get_cached_value("Company", self.company, "default_cash_account")
		expected = [] if default_cash == self.cash_account else [(self.mode, self.cash_account)]
		self.assertEqual(change_account_mismatches(self._till(None)), expected)

	def test_non_cash_modes_are_ignored(self):
		bank = frappe.db.get_value("Mode of Payment", {"type": ["!=", "Cash"]}, "name")
		if not bank:
			self.skipTest("no non-Cash mode of payment")
		doc = self._till(self.cash_account)
		doc.append("payments", {"mode_of_payment": bank})
		self.assertEqual(change_account_mismatches(doc), [])
