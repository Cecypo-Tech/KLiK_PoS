"""A return belongs to the till that refunds it.

The credit note was built from the original sale, so it kept the sale's till (pos_profile)
while taking the refunding shift (custom_pos_opening_entry). Refunded at "Allparts Cashier"
for a sale rung on "Allparts Sales", the cash left the Cashier drawer and was counted in the
Cashier shift - but the note said "Allparts Sales": the dashboard's per-till figures put the
refund on a till whose drawer never paid it, and the Cashier's own closing and history
lists (held to their till) left out a note their totals included.
"""

from unittest.mock import patch

import frappe

from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestReturnTakesTheRefundingTill(CashOnlyReturnCase):
	def setUp(self):
		super().setUp()
		from klik_pos.tests.test_opening_conflict import _profile, _shift

		self.sold_at, self.refunded_at = _profile(), _profile()
		self.shift = _shift(self.refunded_at, "Administrator")

	def _sale_on_other_till(self):
		invoice = self._sale(300, cash=300)
		frappe.db.set_value("Sales Invoice", invoice.name, "pos_profile", self.sold_at, update_modified=False)
		return invoice

	def test_a_full_return_is_the_refunding_till_s(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._full_return(invoice)
		self.assertEqual(credit.custom_pos_opening_entry, self.shift)
		self.assertEqual(credit.pos_profile, self.refunded_at)

	def test_a_partial_return_is_the_refunding_till_s(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._partial_return(invoice, 300)
		self.assertEqual(credit.custom_pos_opening_entry, self.shift)
		self.assertEqual(credit.pos_profile, self.refunded_at)

	def test_with_no_shift_open_the_return_keeps_the_sale_s_till(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=None):
			credit = self._full_return(invoice)
		self.assertEqual(credit.pos_profile, self.sold_at)
