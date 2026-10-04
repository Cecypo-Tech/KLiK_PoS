"""The item tooltip shows stock held at the other warehouses, so the details endpoint lists
every warehouse's quantity even when it is asked about the till's warehouse only."""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item.item_details import get_full_pricing_and_batch_details

ITEM_GROUP = "TEST-STOCK-BY-WH-GROUP"
ITEM_CODE = "TEST-STOCK-BY-WH-ITEM"


class TestStockByWarehouse(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.db.get_value("Warehouse", {"is_group": 0, "company": ["is", "set"]}, "company")
		cls.warehouses = frappe.get_all(
			"Warehouse", filters={"is_group": 0, "company": company}, pluck="name", limit=2
		)

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": ITEM_GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = ITEM_CODE
			item.item_name = ITEM_CODE
			item.item_group = ITEM_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 1
			item.is_sales_item = 1
			item.insert(ignore_permissions=True)

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		cls.stock_entries = [
			make_stock_entry(item_code=ITEM_CODE, target=wh, qty=qty, basic_rate=10, company=company)
			for wh, qty in zip(cls.warehouses, (2, 7))
		]
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for se in reversed(getattr(cls, "stock_entries", [])):
			entry = frappe.get_doc("Stock Entry", se.name)
			if entry.docstatus == 1:
				entry.flags.ignore_permissions = True
				entry.cancel()
			frappe.delete_doc("Stock Entry", se.name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Bin", filters={"item_code": ITEM_CODE}, pluck="name"):
			frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", ITEM_CODE):
			frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
		if frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def test_every_warehouse_is_listed_most_stock_first(self):
		self.assertEqual(len(self.warehouses), 2, "the site needs two leaf warehouses in one company")
		details = get_full_pricing_and_batch_details(ITEM_CODE, warehouse=self.warehouses[0])

		self.assertEqual(
			details["stock_by_warehouse"],
			[
				{"warehouse": self.warehouses[1], "qty": 7.0},
				{"warehouse": self.warehouses[0], "qty": 2.0},
			],
		)
		self.assertEqual(details["global_stock_total"]["total_qty"], 9.0)
