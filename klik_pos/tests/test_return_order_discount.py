"""A credit note reverses the order discount, not adds it.

The return is built with get_mapped_doc, which copies discount_amount as-is. On a sale of
560 discounted by 548.80 (grand 11.20) that left +548.80 on the credit note, so the items'
-560 became -1,108.80: the customer was credited a hundred times what they paid. ERPNext's
make_return_doc negates it; a partial return takes its share by value returned.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import create_partial_return, return_sales_invoice

COMPANY = "_Test Company"
CUSTOMER = "_Test Customer"


class TestReturnReversesOrderDiscount(FrappeTestCase):
	def _sale(self, qty=2, rate=100, discount=50):
		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=1, rate=rate, qty=qty,
			posting_date=frappe.utils.nowdate(), do_not_save=True,
		)
		invoice.apply_discount_on = "Grand Total"
		invoice.discount_amount = discount
		invoice.set("payments", [])
		invoice.insert(ignore_permissions=True)
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": invoice.grand_total})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		self.assertEqual(flt(invoice.grand_total), rate * qty - discount)
		return invoice

	def _credit(self, result):
		self.assertTrue(result.get("success"), result.get("message"))
		return frappe.get_doc("Sales Invoice", result["return_invoice"])

	def test_a_full_return_credits_what_was_paid(self):
		invoice = self._sale()

		credit = self._credit(return_sales_invoice(invoice.name))

		self.assertEqual(flt(credit.discount_amount), -50.0)
		self.assertEqual(flt(credit.grand_total), -150.0)

	def test_every_item_through_the_partial_path_credits_what_was_paid(self):
		invoice = self._sale()
		item = invoice.items[0].item_code

		credit = self._credit(create_partial_return(invoice.name, [{"item_code": item, "return_qty": 2}]))

		self.assertEqual(flt(credit.grand_total), -150.0)

	def test_a_partial_return_takes_its_share_of_the_discount(self):
		invoice = self._sale()
		item = invoice.items[0].item_code

		first = self._credit(create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}]))
		second = self._credit(create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}]))

		self.assertEqual(flt(first.grand_total), -75.0)
		self.assertEqual(flt(first.grand_total) + flt(second.grand_total), -150.0)

	def test_the_tills_unrounded_refund_settles_a_rounded_credit_note(self):
		# POS-01926 on dev: 3 x 430 less 90.30 is 1,199.70 (rounded 1,200). Returning one, the
		# till offers 399.90 but the note rounds to 400 - refunding 399.90 left a 0.10 voucher.
		invoice = self._sale(qty=3, rate=430, discount=90.3)
		item = invoice.items[0].item_code

		credit = self._credit(
			create_partial_return(
				invoice.name, [{"item_code": item, "return_qty": 1}], return_amount=399.9, expected_return_amount=399.9
			)
		)

		self.assertEqual(flt(credit.rounded_total), -400.0)
		self.assertEqual(sum(flt(p.amount) for p in credit.payments), -400.0)
		self.assertEqual(flt(credit.outstanding_amount), 0.0)
