"""A return leaves any money it does not refund in cash on its credit note - the voucher.

No question is asked at return time: cash goes back up to what the drawer kept, and the
rest is a store-credit voucher identified by the credit note number plus the original sale
number - for Walk In too.
"""

from unittest.mock import patch

from klik_pos.api import sales_invoice as si
from klik_pos.api.sales_invoice import create_partial_return, return_sales_invoice
from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestReturnVoucher(CashOnlyReturnCase):
	"""CashOnlyReturnCase provides _sale(total, **tendered): a card-paid sale leaves its whole
	value on the note, a cash-paid one refunds it."""

	def _partial(self, invoice):
		item = invoice.items[0]
		return create_partial_return(
			invoice_name=invoice.name,
			return_items=[{"item_code": item.item_code, "return_qty": item.qty}],
			payment_method="Cash",
			return_amount=0,
		)

	def test_a_card_paid_return_leaves_a_voucher(self):
		invoice = self._sale(500, card=500)
		result = self._partial(invoice)
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			result["credit"], {"note": result["return_invoice"], "original": invoice.name, "available": 500.0}
		)

	def test_a_walkin_card_return_goes_through_and_leaves_a_voucher(self):
		invoice = self._sale(500, card=500)
		with patch.object(si, "_is_walkin_customer", return_value=True):
			result = self._partial(invoice)
		self.assertTrue(result.get("success"), result)
		self.assertEqual(result["credit"]["original"], invoice.name)

	def test_a_full_return_reports_its_voucher_too(self):
		invoice = self._sale(500, card=500)
		result = return_sales_invoice(invoice.name)
		self.assertTrue(result.get("success"), result)
		self.assertEqual(result["credit"]["original"], invoice.name)
		self.assertEqual(result["credit"]["available"], 500.0)

	def test_a_return_refunded_in_cash_leaves_no_voucher(self):
		result = return_sales_invoice(self._sale(600, cash=650).name)
		self.assertTrue(result.get("success"), result)
		self.assertIsNone(result["credit"])

	def test_the_message_names_the_voucher_not_the_invoice(self):
		"""Credit left on the note is a voucher, not a credit to the (already paid) invoice."""
		invoice = self._sale(500, card=500)
		result = self._partial(invoice)
		self.assertIn(f"left as store credit on {result['return_invoice']}", result["message"])
		self.assertNotIn("credited to the invoice", result["message"])

	def test_the_message_shows_money_not_raw_numbers(self):
		from frappe.utils import fmt_money

		invoice = self._sale(500, card=500)
		result = self._partial(invoice)
		self.assertIn(fmt_money(500, currency=invoice.currency), result["message"])
		self.assertNotIn("500.0 ", result["message"])
