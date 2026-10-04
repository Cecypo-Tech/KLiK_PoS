"""Loss of Sale: when a line asks for more than the warehouse holds, sell what is there and
record the rest on the line as LoS Qty."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.setup.pos_profile_fields import install_los_qty_field, install_pos_profile_feature_fields

ITEM_GROUP = "TEST-LOS-GROUP"
STOCKED = "TEST-LOS-STOCKED"  # 10 in the till's warehouse
EMPTY = "TEST-LOS-EMPTY"  # none anywhere
CUSTOMER = "TEST-LOS-CUSTOMER"


def _profile():
	"""The till the session sells from when a shift is open, else any enabled POS Profile."""
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry
	from klik_pos.klik_pos.utils import get_current_pos_profile

	if get_current_pos_opening_entry():
		try:
			return get_current_pos_profile()
		except Exception:
			pass
	name = frappe.db.get_value("POS Profile", {"disabled": 0, "warehouse": ["is", "set"]}, "name")
	return frappe.get_doc("POS Profile", name) if name else None


def _make_item(code):
	if frappe.db.exists("Item", code):
		return
	item = frappe.new_doc("Item")
	item.item_code = code
	item.item_name = code
	item.item_group = ITEM_GROUP
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.is_sales_item = 1
	item.insert(ignore_permissions=True)


class TestLossOfSale(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		install_pos_profile_feature_fields()
		install_los_qty_field()
		frappe.db.commit()
		cls.ready = False
		cls.profile = _profile()
		if not cls.profile:
			return
		cls.warehouse = cls.profile.warehouse
		cls.company = cls.profile.company

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups", "is_group": 0}
			).insert(ignore_permissions=True)
		_make_item(STOCKED)
		_make_item(EMPTY)
		if not frappe.db.exists("Customer", CUSTOMER):
			customer = frappe.new_doc("Customer")
			customer.customer_name = CUSTOMER
			customer.customer_type = "Individual"
			customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
			customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
			customer.insert(ignore_permissions=True)
		cls.customer = CUSTOMER

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		cls.stock_entry = make_stock_entry(
			item_code=STOCKED, target=cls.warehouse, qty=10, basic_rate=10, company=cls.company
		)
		frappe.db.commit()
		cls.ready = True

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "ready", False):
			for name in frappe.get_all(
				"Sales Invoice Item", filters={"item_code": ["in", [STOCKED, EMPTY]]}, pluck="parent", distinct=True
			):
				cls._drop_invoice(name)
			entry = frappe.get_doc("Stock Entry", cls.stock_entry.name)
			if entry.docstatus == 1:
				entry.flags.ignore_permissions = True
				entry.cancel()
			frappe.delete_doc("Stock Entry", entry.name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Bin", filters={"item_code": ["in", [STOCKED, EMPTY]]}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			for code in (STOCKED, EMPTY):
				if frappe.db.exists("Item", code):
					frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
			for doctype, name in (("Item Group", ITEM_GROUP), ("Customer", CUSTOMER)):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	@staticmethod
	def _drop_invoice(name):
		if not name or not frappe.db.exists("Sales Invoice", name):
			return
		invoice = frappe.get_doc("Sales Invoice", name)
		if invoice.docstatus == 1:
			invoice.flags.ignore_permissions = True
			invoice.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no enabled POS Profile with a warehouse on this site")
		frappe.set_user("Administrator")

	# Task 1

	def test_the_fields_exist(self):
		field = frappe.get_meta("Sales Invoice Item").get_field("custom_los_qty")
		self.assertIsNotNone(field)
		self.assertEqual((field.fieldtype, field.read_only, field.in_list_view, field.no_copy), ("Float", 1, 1, 1))
		self.assertIsNotNone(frappe.get_meta("POS Profile").get_field("custom_enable_loss_of_sale"))
		self.assertFalse(install_los_qty_field(), "a second install must be a no-op")

	def test_available_stock_is_net_of_reservations(self):
		from klik_pos.api.sales_invoice import get_available_stock_map

		keys = {(STOCKED, self.warehouse), (EMPTY, self.warehouse)}
		stock = get_available_stock_map(keys)
		self.assertEqual(stock[(STOCKED, self.warehouse)].available_qty, 10)
		self.assertEqual(stock[(EMPTY, self.warehouse)].available_qty, 0)

		with patch(
			"klik_pos.api.sales_invoice.get_reserved_stock_map",
			return_value={(STOCKED, self.warehouse): 4},
		):
			row = get_available_stock_map(keys)[(STOCKED, self.warehouse)]
		self.assertEqual((row.actual_qty, row.reserved_qty, row.available_qty), (10, 4, 6))
