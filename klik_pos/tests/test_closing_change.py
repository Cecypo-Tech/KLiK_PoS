"""Change handed back comes out of the drawer's expected cash.

The payment row keeps what the customer tendered (650 for a 600 sale); the 50 change is
recorded on the invoice (change_amount, from account_for_change_amount). ERPNext's own POS
Closing Entry subtracts it from the mode paying into that account (pos_closing_entry.py,
get_payments); klik's closing screen and shift summary summed the rows alone and expected
650 in a drawer holding 600.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.payment import _fetch_daily_sales_data, _fetch_opening_sales_data
from klik_pos.api.pos_entry import _calculate_payment_reconciliation
from klik_pos.tests.test_mpesa_payment_entry_first import MpesaFirstCase


class TestChangeLeavesTheDrawer(MpesaFirstCase):
	def setUp(self):
		super().setUp()
		self.shift = f"TEST-OPE-CHG-{frappe.generate_hash(length=6)}"

	def _cash_sale(self, total, tendered):
		invoice = self._draft(rate=total)
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": tendered})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		frappe.db.set_value(
			"Sales Invoice",
			invoice.name,
			{"custom_pos_opening_entry": self.shift, "pos_profile": self.profile_name()},
			update_modified=False,
		)
		return invoice

	def profile_name(self):
		return f"TEST-PROFILE-{self.shift}"

	def test_the_sale_records_the_change(self):
		invoice = self._cash_sale(600, 650)
		self.assertEqual(flt(invoice.change_amount), 50, "fixture: ERPNext worked out the change")
		self.assertTrue(invoice.account_for_change_amount)

	def test_closing_expects_the_cash_kept_not_the_cash_tendered(self):
		self._cash_sale(600, 650)
		rows = _calculate_payment_reconciliation(frappe._dict(name=self.shift), {"closing_balance": {"Cash": 600}})
		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")
		self.assertEqual(flt(cash["expected_amount"]), 600)
		self.assertEqual(flt(cash["difference"]), 0)

	def test_the_shift_summary_counts_the_cash_kept(self):
		self._cash_sale(600, 650)
		self._cash_sale(300, 300)
		rows = {r["mode_of_payment"]: r for r in _fetch_opening_sales_data(self.shift)}
		self.assertEqual(flt(rows["Cash"]["total_amount"]), 900)

	def test_the_daily_summary_counts_the_cash_kept(self):
		invoice = self._cash_sale(600, 650)
		rows = {r["mode_of_payment"]: r for r in _fetch_daily_sales_data(self.profile_name(), invoice.posting_date)}
		self.assertEqual(flt(rows["Cash"]["total_amount"]), 600)

	def test_the_invoice_list_names_the_change_on_the_row_it_left_through(self):
		"""The Closing Shift cards add up the invoice list's payment rows; the row keeps the
		tendered amount for the receipt and says how much of it went back as change."""
		from klik_pos.api.sales_invoice import _batch_fetch_payment_methods

		invoice = self._cash_sale(600, 650)
		rows = _batch_fetch_payment_methods([invoice.name])[invoice.name]
		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")
		self.assertEqual(flt(cash["amount"]), 650)
		self.assertEqual(flt(cash["change_amount"]), 50)
