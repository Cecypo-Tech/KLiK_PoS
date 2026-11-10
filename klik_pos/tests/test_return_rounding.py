"""A partial return credits exactly what came back; only the return that finishes the sale rounds.

Each credit note used to round on its own: a 617.50 line came back as a 618 note (the dialog
had said 617.50), and a sale of 2897.50 rounded to 2898 returned line by line in notes adding
up to 2899 - more than was paid.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.sales_invoice import create_partial_return
from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestReturnRounding(CashOnlyReturnCase):
	def _rounded_sale(self):
		sale = self._draft(rate=100.25, qty=2, posting_date=frappe.utils.nowdate())
		sale.save(ignore_permissions=True)
		if not flt(sale.rounding_adjustment):
			self.skipTest("rounded totals are off on this site")
		sale.append("payments", {"mode_of_payment": "Cash", "amount": sale.rounded_total})
		sale.save(ignore_permissions=True)
		sale.submit()
		return sale

	def _return(self, sale, qty):
		row = sale.items[0]
		result = create_partial_return(
			invoice_name=sale.name, return_items=[{"item_code": row.item_code, "name": row.name, "return_qty": qty}]
		)
		self.assertTrue(result.get("success"), result.get("message") or result.get("error"))
		return frappe.get_doc("Sales Invoice", result["return_invoice"])

	def test_a_partial_return_credits_its_exact_value(self):
		credit = self._return(self._rounded_sale(), 1)
		self.assertTrue(credit.disable_rounded_total)
		self.assertEqual(flt(credit.grand_total), -100.25)

	def test_the_return_that_finishes_the_sale_rounds(self):
		sale = self._rounded_sale()
		self._return(sale, 1)
		last = self._return(sale, 1)
		self.assertFalse(last.disable_rounded_total)
