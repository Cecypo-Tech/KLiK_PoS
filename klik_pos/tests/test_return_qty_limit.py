"""A sale's lines can be returned at most once, whatever the till's dialog believed.

The till's return builders linked each credit-note line to the sale through a field that does
not exist on Sales Invoice Item, so ERPNext's own return check (validate_returned_items)
found no original line and never compared quantities: a stale dialog, a second tab or a
direct call could return more than was sold, or the same units twice.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.sales_invoice import create_partial_return
from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class TestReturnQtyLimit(CashOnlyReturnCase):
	def _cash_sale(self, qty=4, rate=100):
		invoice = self._draft(rate=rate, qty=qty, posting_date=frappe.utils.nowdate())
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": qty * rate})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		return invoice

	def _return(self, invoice, *lines):
		"""lines: (item row, qty)."""
		return create_partial_return(
			invoice_name=invoice.name,
			return_items=[{"item_code": row.item_code, "name": row.name, "return_qty": qty} for row, qty in lines],
		)

	def test_returning_more_than_was_sold_is_refused(self):
		sale = self._cash_sale(qty=4)
		result = self._return(sale, (sale.items[0], 5))
		self.assertFalse(result.get("success"), "5 of 4 units must not come back")

	def test_units_already_returned_cannot_be_returned_again(self):
		sale = self._cash_sale(qty=4)
		self.assertTrue(self._return(sale, (sale.items[0], 3)).get("success"))
		self.assertFalse(self._return(sale, (sale.items[0], 2)).get("success"), "only 1 unit is left")
		self.assertTrue(self._return(sale, (sale.items[0], 1)).get("success"), "the last unit still can")

	def test_the_credit_note_line_names_the_sale_line(self):
		sale = self._cash_sale(qty=2)
		result = self._return(sale, (sale.items[0], 1))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual(credit.items[0].sales_invoice_item, sale.items[0].name)

	def test_the_same_item_on_two_lines_returns_the_line_picked(self):
		"""Grid tills may sell one item on two lines at two prices."""
		sale = self._draft(rate=100, qty=1, posting_date=frappe.utils.nowdate())
		sale.append("items", {**sale.items[0].as_dict(), "name": None, "idx": 2, "rate": 60, "price_list_rate": 60})
		sale.append("payments", {"mode_of_payment": "Cash", "amount": 160})
		sale.save(ignore_permissions=True)
		sale.submit()
		cheap = next(row for row in sale.items if flt(row.rate) == 60)

		result = self._return(sale, (cheap, 1))
		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([(r.sales_invoice_item, flt(r.rate)) for r in credit.items], [(cheap.name, 60)])
