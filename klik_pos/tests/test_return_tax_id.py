"""A credit note keeps the tax ID printed on the sale it reverses.

Sales Invoice.tax_id is fetched from Customer.tax_id on every draft save. A walk-in sale
carries a tax ID the Customer record does not have, so the draft save that builds the credit
note wiped it while the walk-in name and phone (no fetch_from) survived. Fixtures mirror
test_mpesa_payment_entry_first: _Test Company; the sale is dated today so the return
can follow it.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import create_partial_return, return_sales_invoice

COMPANY = "_Test Company"
CUSTOMER = "_Test Customer"
TAX_ID = "A987654321Z"


class TestReturnCarriesTaxId(FrappeTestCase):
	def _sale(self, qty=1):
		# The Customer record has no tax ID; the sale got one at the till, the way
		# create_and_submit_invoice stamps it after insert and before submit.
		self.assertFalse(frappe.db.get_value("Customer", CUSTOMER, "tax_id"))
		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=0, rate=100, qty=qty,
			posting_date=frappe.utils.nowdate(), do_not_save=True,
		)
		invoice.insert(ignore_permissions=True)
		invoice.db_set("tax_id", TAX_ID)
		invoice.submit()
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "tax_id"), TAX_ID)
		return invoice

	def test_a_full_return_keeps_the_sale_s_tax_id(self):
		invoice = self._sale()

		result = return_sales_invoice(invoice.name)

		self.assertTrue(result.get("success"), result.get("message"))
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["return_invoice"], "tax_id"), TAX_ID)

	def test_a_partial_return_keeps_the_sale_s_tax_id(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}])

		self.assertTrue(result.get("success"), result.get("message"))
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["return_invoice"], "tax_id"), TAX_ID)
