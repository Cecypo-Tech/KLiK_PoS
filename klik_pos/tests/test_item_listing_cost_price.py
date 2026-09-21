"""get_items must surface each item's warehouse-scoped valuation rate as `cost_price`.

The POS item list has no cost/valuation field at all today - only the per-item tooltip
endpoint (get_full_pricing_and_batch_details) computes one, via a weighted-average-over-SLEs
calc that's too heavy to run for every row of a paginated list. The list column instead reads
Bin.valuation_rate directly: cheap, warehouse-scoped, and already maintained by Frappe stock.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_listing

ITEM_GROUP = "TEST-COST-PRICE-GROUP"
ITEM_CODES = [f"TEST-COST-PRICE-ITEM-{i:03d}" for i in range(1, 3)]
# Stocked by the Nos, sold by the Box of 12: the list reports this one in its sales UOM.
BOX_ITEM_CODE = "TEST-COST-PRICE-ITEM-BOX"
BOX_FACTOR = 12
ALL_ITEM_CODES = [*ITEM_CODES, BOX_ITEM_CODE]


class ItemListingCostPriceTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0, "company": cls.company}, "name")
		cls.other_warehouse = frappe.db.get_value(
			"Warehouse",
			{"is_group": 0, "company": cls.company, "name": ["!=", cls.warehouse]},
			"name",
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

		for code in ALL_ITEM_CODES:
			if not frappe.db.exists("Item", code):
				item = frappe.new_doc("Item")
				item.item_code = code
				item.item_name = code
				item.item_group = ITEM_GROUP
				item.stock_uom = "Nos"
				item.is_stock_item = 1
				item.is_sales_item = 1
				if code == BOX_ITEM_CODE:
					item.sales_uom = "Box"
					item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
					item.append("uoms", {"uom": "Box", "conversion_factor": BOX_FACTOR})
				item.insert(ignore_permissions=True)

			bin_name = frappe.db.get_value("Bin", {"item_code": code, "warehouse": cls.warehouse}, "name")
			if not bin_name:
				bin_name = (
					frappe.get_doc({"doctype": "Bin", "item_code": code, "warehouse": cls.warehouse})
					.insert(ignore_permissions=True)
					.name
				)
			frappe.db.set_value("Bin", bin_name, "actual_qty", 10, update_modified=False)

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for code in ALL_ITEM_CODES:
			for bin_name in frappe.get_all("Bin", filters={"item_code": code}, pluck="name"):
				frappe.db.set_value("Bin", bin_name, "actual_qty", 0, update_modified=False)
				frappe.delete_doc("Bin", bin_name, force=True, ignore_permissions=True)
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
		if frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()


class TestFetchBatchCostPrice(ItemListingCostPriceTestCase):
	def test_returns_valuation_rate_for_the_requested_warehouse(self):
		bin_name = frappe.db.get_value(
			"Bin", {"item_code": ITEM_CODES[0], "warehouse": self.warehouse}, "name"
		)
		frappe.db.set_value("Bin", bin_name, "valuation_rate", 12.5, update_modified=False)
		frappe.db.commit()

		cost_map = item_listing._fetch_batch_cost_price(ITEM_CODES, self.warehouse)

		self.assertEqual(cost_map.get(ITEM_CODES[0]), 12.5)

	def test_item_with_no_bin_row_is_absent_from_the_map(self):
		cost_map = item_listing._fetch_batch_cost_price(["TEST-COST-PRICE-ITEM-DOES-NOT-EXIST"], self.warehouse)

		self.assertEqual(cost_map, {})

	def test_empty_inputs_return_empty_map(self):
		self.assertEqual(item_listing._fetch_batch_cost_price([], self.warehouse), {})
		self.assertEqual(item_listing._fetch_batch_cost_price(ITEM_CODES, None), {})

	def test_is_scoped_to_the_requested_warehouse(self):
		if not self.other_warehouse:
			self.skipTest("test site has only one non-group warehouse")

		bin_name = frappe.db.get_value(
			"Bin", {"item_code": ITEM_CODES[0], "warehouse": self.warehouse}, "name"
		)
		frappe.db.set_value("Bin", bin_name, "valuation_rate", 12.5, update_modified=False)
		frappe.db.commit()

		cost_map = item_listing._fetch_batch_cost_price(ITEM_CODES, self.other_warehouse)

		self.assertNotIn(ITEM_CODES[0], cost_map)


class TestGetItemsCostPrice(ItemListingCostPriceTestCase):
	def _set_valuation(self, code, rate):
		bin_name = frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "name")
		frappe.db.set_value("Bin", bin_name, "valuation_rate", rate, update_modified=False)
		frappe.db.commit()

	def _items(self, hide_cost=0):
		pos_doc = frappe._dict(
			name="TEST-COST-PRICE-PROFILE",
			company=self.company,
			warehouse=self.warehouse,
			selling_price_list=frappe.db.get_value("Price List", {"selling": 1}, "name"),
			item_groups=[],
			custom_enable_service_items=0,
			custom_enhanced_search=0,
			is_tax_included_in_basic_rate=0,
			taxes_and_charges=None,
			restrict_cost_visibility_in_tooltip=hide_cost,
		)
		context = (pos_doc, self.warehouse, pos_doc.selling_price_list, False)
		with patch.object(item_listing, "_get_pos_context", return_value=context):
			result = item_listing.get_items(category=ITEM_GROUP)
		return {item["id"]: item for item in result["items"]}

	def test_payload_carries_the_warehouse_valuation(self):
		self._set_valuation(ITEM_CODES[0], 12.5)

		self.assertEqual(self._items()[ITEM_CODES[0]]["cost_price"], 12.5)

	def test_cost_is_per_the_uom_the_rate_is_quoted_in(self):
		"""Bin values stock per stock UOM; a row listed by the Box must cost a Box."""
		self._set_valuation(BOX_ITEM_CODE, 10)

		item = self._items()[BOX_ITEM_CODE]

		self.assertEqual(item["uom"], "Box")
		self.assertEqual(item["cost_price"], 10 * BOX_FACTOR)

	def test_cost_is_not_sent_when_the_profile_hides_it(self):
		"""Hide Cost Price must keep the figure off the wire, not just off the screen."""
		self._set_valuation(ITEM_CODES[0], 12.5)

		with patch.object(item_listing, "_fetch_batch_cost_price") as fetch:
			item = self._items(hide_cost=1)[ITEM_CODES[0]]

		fetch.assert_not_called()
		self.assertEqual(item["cost_price"], 0)
