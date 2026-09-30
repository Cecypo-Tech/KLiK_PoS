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


	def _card_on_the_cash_account(self):
		from klik_pos.tests.test_mpesa_payment_entry_first import COMPANY

		cash_account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": "Cash", "company": COMPANY}, "default_account"
		)
		mode = frappe.get_doc("Mode of Payment", "Credit Card")
		if not mode.get("accounts", {"company": COMPANY}):
			mode.append("accounts", {"company": COMPANY, "default_account": cash_account})
			mode.save(ignore_permissions=True)
		return cash_account

	def _split_sale(self, card_amount, cash_amount, total):
		"""Credit Card first, then Cash - both paying into the same ledger account."""
		self._card_on_the_cash_account()
		invoice = self._draft(rate=total)
		invoice.append("payments", {"mode_of_payment": "Credit Card", "amount": card_amount})
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": cash_amount})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		frappe.db.set_value(
			"Sales Invoice",
			invoice.name,
			{"custom_pos_opening_entry": self.shift, "pos_profile": self.profile_name()},
			update_modified=False,
		)
		return invoice

	def test_change_comes_off_the_cash_row_when_another_mode_shares_its_account(self):
		"""Card 500 + Cash 150 for a 600 sale: the 50 change went back as cash, not card."""
		invoice = self._split_sale(500, 150, 600)
		self.assertEqual(flt(invoice.change_amount), 50, "fixture: ERPNext worked out the change")
		rows = {r["mode_of_payment"]: r for r in _fetch_opening_sales_data(self.shift)}
		self.assertEqual(flt(rows["Cash"]["total_amount"]), 100)
		self.assertEqual(flt(rows["Credit Card"]["total_amount"]), 500)

	def test_the_list_row_carrying_the_change_is_the_cash_row(self):
		from klik_pos.api.sales_invoice import _batch_fetch_payment_methods

		invoice = self._split_sale(500, 150, 600)
		rows = {r["mode_of_payment"]: r for r in _batch_fetch_payment_methods([invoice.name])[invoice.name]}
		self.assertEqual(flt(rows["Cash"].get("change_amount")), 50)
		self.assertFalse(rows["Credit Card"].get("change_amount"))

	def test_change_comes_off_the_cash_row_when_no_row_pays_into_the_change_account(self):
		"""A profile whose change account is not the Cash mode's account: the change still
		left the drawer, through the invoice's Cash row."""
		invoice = self._cash_sale(600, 650)
		frappe.db.set_value("Sales Invoice", invoice.name, "account_for_change_amount", "_Test Bank - _TC")
		rows = _calculate_payment_reconciliation(frappe._dict(name=self.shift), {"closing_balance": {"Cash": 600}})
		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")
		self.assertEqual(flt(cash["expected_amount"]), 600)
