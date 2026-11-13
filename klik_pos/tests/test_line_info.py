"""The grid till's side panel shows the facts a till's POS Profile lists, in that order.
Built-ins are named; anything else is an Item field, read only when the user may read it."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import line_info
from klik_pos.api.item.line_info import DEFAULT_LINE_INFO, line_info_keys, resolve_line_info

ITEM_GROUP = "TEST-LINE-INFO-GROUP"
ITEM_CODE = "TEST-LINE-INFO-ITEM"


class TestLineInfo(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Warehouse", {"is_group": 0, "company": ["is", "set"]}, "company")
		cls.warehouses = frappe.get_all(
			"Warehouse", filters={"is_group": 0, "company": cls.company}, pluck="name", limit=2
		)
		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Box"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Box"}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.update(
				{
					"item_code": ITEM_CODE, "item_name": ITEM_CODE, "item_group": ITEM_GROUP,
					"stock_uom": "Nos", "is_stock_item": 1, "description": "<p>Tonic <b>water</b></p>",
				}
			)
			item.append("uoms", {"uom": "Box", "conversion_factor": 24})
			item.insert(ignore_permissions=True)

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		for wh, qty in zip(cls.warehouses, (3, 5)):
			make_stock_entry(item_code=ITEM_CODE, target=wh, qty=qty, basic_rate=10, company=cls.company)

	def _info(self, keys):
		return resolve_line_info(ITEM_CODE, keys, self.company, "Administrator")

	def test_empty_list_means_the_default_list(self):
		self.assertEqual(line_info_keys([]), DEFAULT_LINE_INFO)
		self.assertEqual(line_info_keys(["brand", " ", "uoms"]), ["brand", "uoms"])

	def test_rows_keep_the_list_order_with_item_fields_formatted(self):
		rows = self._info(["item_group", "in_stock", "description"])["rows"]
		self.assertEqual([r["key"] for r in rows], ["item_group", "in_stock", "description"])
		self.assertEqual(rows[0]["value"], ITEM_GROUP)
		self.assertEqual(rows[2]["value"], "Tonic water")  # HTML stripped
		self.assertEqual(rows[2]["label"], "Description")

	def test_unknown_layout_and_empty_fields_are_dropped(self):
		rows = self._info(["no_such_field", "section_break_11", "brand", "uoms"])["rows"]
		self.assertEqual([r["key"] for r in rows], ["uoms"])  # brand is empty on this item

	def test_a_field_the_user_cannot_read_is_dropped(self):
		df = frappe.get_meta("Item").get_field("item_group")
		with patch.object(df, "permlevel", 7):
			rows = self._info(["item_group", "description"])["rows"]
		self.assertEqual([r["key"] for r in rows], ["description"])

	def test_warehouses_only_those_the_user_may_see(self):
		with patch.object(line_info, "leaf_warehouses_for", return_value=[self.warehouses[1]]):
			info = self._info(["warehouses"])
		self.assertEqual(info["warehouses"], [{"warehouse": self.warehouses[1], "qty": 5}])

	def test_uoms_with_conversions(self):
		info = self._info(["uoms"])
		self.assertEqual(info["stock_uom"], "Nos")
		self.assertIn({"uom": "Box", "conversion_factor": 24}, info["uoms"])

	def test_lists_are_skipped_when_not_asked_for(self):
		info = self._info(["description"])
		self.assertEqual((info["warehouses"], info["uoms"]), ([], []))
