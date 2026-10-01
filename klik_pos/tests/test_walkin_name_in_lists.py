"""Invoice History names the walk-in buyer, not just "Walk In".

With every walk-in sale and held order under one customer, the list could not tell them
apart - and a held order has to be found again to be resumed.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import get_sales_invoices
from klik_pos.api.sales_order import get_held_orders
from klik_pos.tests.test_held_order_visibility import _held_order

FIELD = "custom_walkin_customer_name"


class TestHeldOrdersCarryTheWalkinName(FrappeTestCase):
	def setUp(self):
		if not frappe.db.has_column("Sales Order", FIELD):
			self.skipTest("no walk-in name field on this site")
		self.name = f"Buyer {frappe.generate_hash(length=6)}"
		self.so = _held_order()
		frappe.db.set_value("Sales Order", self.so.name, FIELD, self.name, update_modified=False)

	def test_the_row_carries_it(self):
		rows = {r["name"]: r for r in get_held_orders(skip_opening_entry_filter=True, limit=200)["data"]}
		self.assertEqual(rows[self.so.name][FIELD], self.name)

	def test_search_finds_the_order_by_it(self):
		rows = get_held_orders(skip_opening_entry_filter=True, search=self.name.lower(), limit=200)["data"]
		self.assertEqual([r["name"] for r in rows], [self.so.name])


class TestInvoicesCarryTheWalkinName(FrappeTestCase):
	def setUp(self):
		if not frappe.db.has_column("Sales Invoice", FIELD):
			self.skipTest("no walk-in name field on this site")
		self.name = f"Buyer {frappe.generate_hash(length=6)}"
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={"docstatus": 1, "custom_pos_opening_entry": ["!=", ""]},
			pluck="name",
			order_by="creation desc",
			limit=1,
		)
		if not invoices:
			self.skipTest("no POS invoice on this site")
		self.invoice = invoices[0]
		frappe.db.set_value("Sales Invoice", self.invoice, FIELD, self.name, update_modified=False)

	def test_search_finds_the_invoice_by_it_and_returns_it(self):
		result = get_sales_invoices(search=self.name, skip_opening_entry_filter=True, surface="history")
		self.assertTrue(result["success"], msg=result.get("error"))
		rows = {r["name"]: r for r in result["data"]}
		self.assertIn(self.invoice, rows)
		self.assertEqual(rows[self.invoice][FIELD], self.name)
