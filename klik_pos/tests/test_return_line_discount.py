"""Partial returns of sales with a line discount, and of sales paid by cheque.

A line discount lowers the item's rate (list 100 less 10% sells at 90), so a partial return
credits the discounted rate it was sold at, never the list price. A cheque is a Bank-type
mode like a card: the till hands back no cash for it, and its value stays on the credit
note as the customer's voucher.
"""

import frappe
from frappe.utils import flt

from klik_pos.tests.test_mpesa_payment_entry_first import MODE as CHEQUE
from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestPartialReturnOfDiscountedOrChequeSale(CashOnlyReturnCase):
	def _sale(self, qty=4, list_rate=100, discount_pct=0, **tendered):
		"""A submitted sale today of qty x list_rate less discount_pct per line, paid {mode: amount}."""
		invoice = self._draft(rate=list_rate, qty=qty, posting_date=frappe.utils.nowdate())
		line = invoice.items[0]
		line.price_list_rate = list_rate
		line.discount_percentage = discount_pct
		# As the till sends it: ERPNext derives the rate from the discount only when no rate is set.
		line.rate = flt(list_rate * (1 - discount_pct / 100), 2)
		modes = {"cash": "Cash", "cheque": CHEQUE}
		for mode, amount in tendered.items():
			invoice.append("payments", {"mode_of_payment": modes[mode], "amount": amount})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		return invoice

	def _partial_return_qty(self, invoice, qty, refund):
		from klik_pos.api.sales_invoice import create_partial_return

		result = create_partial_return(
			invoice_name=invoice.name,
			return_items=[{"item_code": invoice.items[0].item_code, "return_qty": qty}],
			payment_method="Cash",
			return_amount=refund,
		)
		self.assertTrue(result.get("success"), result.get("message") or result.get("error"))
		return frappe.get_doc("Sales Invoice", result["return_invoice"])

	def test_a_line_discounted_partial_return_credits_the_discounted_rate(self):
		invoice = self._sale(discount_pct=10, cash=360)
		self.assertEqual(flt(invoice.items[0].rate), 90.0, "the line sold at list less 10%")
		self.assertEqual(flt(invoice.grand_total), 360.0)

		credit = self._partial_return_qty(invoice, 1, 90)

		self.assertEqual(flt(credit.grand_total), -90.0, "the discounted rate, not the list 100")
		self.assertEqual(flt(credit.items[0].rate), 90.0)

	def test_a_line_discounted_partial_return_refunds_that_in_cash_and_owes_nothing(self):
		invoice = self._sale(discount_pct=10, cash=360)

		first = self._partial_return_qty(invoice, 1, 90)
		rest = self._partial_return_qty(invoice, 3, 270)

		self.assertEqual(self._refund_rows(first), [("Cash", -90.0)])
		self.assertEqual(flt(first.outstanding_amount), 0.0, "fully refunded, no voucher left")
		self.assertEqual(self._refund_rows(rest), [("Cash", -270.0)])
		self.assertEqual(flt(first.grand_total) + flt(rest.grand_total), -360.0, "never more than was paid")

	def test_a_cheque_paid_partial_return_pays_no_cash_and_leaves_a_voucher(self):
		invoice = self._sale(cheque=400)

		credit = self._partial_return_qty(invoice, 1, 100)

		self.assertEqual(self._refund_rows(credit), [], "a cheque is not paid back from the drawer")
		self.assertEqual(flt(abs(credit.outstanding_amount)), 100.0, "its value stays as credit")

	def test_a_discounted_cash_and_cheque_sale_refunds_its_cash_first_then_credits(self):
		"""4 x 90 = 360, paid Cash 180 + Cheque 180. Returning 3 (270): 180 cash back, 90 as credit."""
		invoice = self._sale(discount_pct=10, cash=180, cheque=180)

		credit = self._partial_return_qty(invoice, 3, 270)

		self.assertEqual(flt(credit.grand_total), -270.0)
		self.assertEqual(self._refund_rows(credit), [("Cash", -180.0)], "only the cash the drawer kept")
		self.assertEqual(flt(abs(credit.outstanding_amount)), 90.0, "the cheque share stays owed")
