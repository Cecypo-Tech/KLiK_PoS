"""A POS return applied to its original carries no outstanding of its own.

With `update_outstanding_for_self` off, ERPNext books the return's Debtors legs - the
credit and any cash handed back - against the original, so the ledger reduces the
original's outstanding and the return has none. ERPNext zeroes the return's own field only
for non-POS returns, so a POS return used to keep -grand_total there and the same credit
read as owed twice: once off the original, once as a refund still owed on the note.
"""

import frappe
from frappe.utils import flt

from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


def _ledger_outstanding(voucher):
	return flt(
		frappe.db.sql(
			"""select sum(amount_in_account_currency) from `tabPayment Ledger Entry`
			where against_voucher_type='Sales Invoice' and against_voucher_no=%s and delinked=0""",
			voucher,
		)[0][0]
	)


class TestReturnOwnOutstanding(CashOnlyReturnCase):
	def test_a_returned_credit_sale_leaves_nothing_outstanding_anywhere(self):
		# A credit sale still carries its till's payment rows, all at 0
		original = self._sale(300, cash=0)
		credit = self._full_return(original)

		self.assertEqual(credit.update_outstanding_for_self, 0, "the credit goes onto the original")
		self.assertEqual(flt(original.reload().outstanding_amount), 0)
		self.assertEqual(flt(credit.outstanding_amount), 0, "the note owes nothing of its own")
		self.assertEqual(_ledger_outstanding(credit.name), 0)

	def test_a_part_cash_refund_leaves_the_note_with_no_outstanding(self):
		"""Sold 600, paid 200 cash: a full return hands the 200 back and credits the other 400."""
		original = self._sale(600, cash=200)
		credit = self._full_return(original)

		self.assertEqual(self._refund_rows(credit), [("Cash", -200)])
		self.assertEqual(credit.update_outstanding_for_self, 0)
		self.assertEqual(flt(original.reload().outstanding_amount), 0)
		self.assertEqual(flt(credit.outstanding_amount), 0)
		self.assertEqual(_ledger_outstanding(credit.name), 0)

	def test_credit_kept_on_the_note_still_reads_as_owed(self):
		credit = self._full_return(self._sale(500, card=500))

		self.assertEqual(credit.update_outstanding_for_self, 1)
		self.assertEqual(flt(credit.outstanding_amount), -500)
		self.assertEqual(_ledger_outstanding(credit.name), -500)


class TestPatchExistingReturns(CashOnlyReturnCase):
	def test_patch_resets_a_stale_note_and_leaves_a_real_credit(self):
		from klik_pos.patches.v16_0.zero_pos_return_own_outstanding import execute

		stale = self._full_return(self._sale(300, cash=0))
		frappe.db.set_value("Sales Invoice", stale.name, "outstanding_amount", -300, update_modified=False)
		owed = self._full_return(self._sale(500, card=500))

		execute()

		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", stale.name, "outstanding_amount")), 0)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", owed.name, "outstanding_amount")), -500)
