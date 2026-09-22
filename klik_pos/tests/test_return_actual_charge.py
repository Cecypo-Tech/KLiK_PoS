"""A credit note reverses a fixed ("Actual") charge, not just the percentage taxes.

A POS sale with a Shipping Rule carries the courier fee as an Actual tax row. The mapper
copied it as-is, calculate_taxes_and_totals left it positive, and ERPNext then rejected the
return's payment row. ERPNext's own make_return_doc flips Actual rows; so do we now - but
only when the whole order comes back. The delivery happened, so a partial return keeps the
fee: the credit note carries the returned items and nothing else.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import (
	create_partial_return,
	get_customer_invoices_for_return,
	get_invoice_details,
	return_sales_invoice,
)

COMPANY = "_Test Company"
CUSTOMER = "_Test Customer"
COURIER = 150.0


class TestReturnReversesActualCharge(FrappeTestCase):
	def _sale(self, qty=1, rate=100):
		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=1, rate=rate, qty=qty,
			posting_date=frappe.utils.nowdate(), do_not_save=True,
		)
		invoice.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": "_Test Account Shipping Charges - _TC",
				"description": "Courier",
				"tax_amount": COURIER,
			},
		)
		invoice.set("payments", [])
		invoice.insert(ignore_permissions=True)
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": invoice.grand_total})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		self.assertEqual(flt(invoice.grand_total), rate * qty + COURIER)
		return invoice

	def test_a_full_return_reverses_the_whole_sale_including_the_courier_fee(self):
		invoice = self._sale()

		result = return_sales_invoice(invoice.name)

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual(flt(credit.grand_total), -flt(invoice.grand_total))
		self.assertEqual([flt(t.tax_amount) for t in credit.taxes if t.charge_type == "Actual"], [-COURIER])
		self.assertEqual([flt(p.amount) for p in credit.payments], [-flt(invoice.grand_total)])

	def test_a_partial_return_keeps_the_courier_fee(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}])

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([t.charge_type for t in credit.taxes if t.charge_type == "Actual"], [], "fee not on the note")
		self.assertEqual(flt(credit.grand_total), -100.0, "only the returned item is credited")

	def test_returning_every_item_through_the_partial_path_reverses_the_fee(self):
		# The till has no separate "return all" call: a full return is the partial path with
		# every quantity selected.
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 2}])

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([flt(t.tax_amount) for t in credit.taxes if t.charge_type == "Actual"], [-COURIER])
		self.assertEqual(flt(credit.grand_total), -flt(invoice.grand_total))


class TestCashierChoosesTheFixedCharge(FrappeTestCase):
	"""The courier fee is a line the cashier ticks, like an item. When the till says nothing
	(older clients), the quantity rule above still decides."""

	_sale = TestReturnReversesActualCharge._sale

	def test_the_fee_comes_back_with_one_item_when_ticked(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], return_fixed_charges=1)

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([flt(t.tax_amount) for t in credit.taxes if t.charge_type == "Actual"], [-COURIER])
		self.assertEqual(flt(credit.grand_total), -(100 + COURIER))

	def test_the_fee_stays_on_a_full_return_when_unticked(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 2}], return_fixed_charges=0)

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([t.charge_type for t in credit.taxes if t.charge_type == "Actual"], [])
		self.assertEqual(flt(credit.grand_total), -200.0)

	def test_the_fee_cannot_be_reversed_twice(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code
		first = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], return_fixed_charges=1)
		self.assertTrue(first.get("success"), first.get("message"))

		second = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], return_fixed_charges=1)

		self.assertFalse(second.get("success"))
		self.assertIn(first["return_invoice"], second.get("message") or "")

	def test_the_picker_lists_the_fee_and_who_reversed_it(self):
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code
		# The picker only offers invoices rung up on a till.
		frappe.db.set_value(
			"Sales Invoice", invoice.name, "custom_pos_opening_entry", "POS-OPE-TEST-FEE", update_modified=False
		)

		def picked():
			result = get_customer_invoices_for_return(CUSTOMER)
			self.assertTrue(result["success"], result.get("error"))
			return next(r for r in result["data"] if r["name"] == invoice.name)

		charges = picked()["fixed_charges"]
		self.assertEqual(len(charges), 1)
		self.assertEqual(charges[0]["description"], "Courier")
		self.assertEqual(flt(charges[0]["amount"]), COURIER)
		self.assertIsNone(charges[0]["reversed_by"])

		credit = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], return_fixed_charges=1)
		self.assertTrue(credit.get("success"), credit.get("message"))

		self.assertEqual(picked()["fixed_charges"][0]["reversed_by"], credit["return_invoice"])

	def test_the_invoice_detail_lists_the_fee_the_same_way(self):
		# The single-invoice return dialog reads the detail endpoint, not the picker.
		invoice = self._sale(qty=2)
		item = invoice.items[0].item_code

		def detail():
			result = get_invoice_details(invoice.name)
			self.assertTrue(result.get("success"), result.get("message"))
			return (result.get("data") or {}).get("data") or result["data"]

		charges = detail()["fixed_charges"]
		self.assertEqual([(c["description"], flt(c["amount"]), c["reversed_by"]) for c in charges], [("Courier", COURIER, None)])

		credit = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], return_fixed_charges=1)
		self.assertTrue(credit.get("success"), credit.get("message"))

		self.assertEqual(detail()["fixed_charges"][0]["reversed_by"], credit["return_invoice"])
