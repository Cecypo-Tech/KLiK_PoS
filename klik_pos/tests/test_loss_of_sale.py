"""Loss of Sale: when a line asks for more than the warehouse holds, sell what is there and
record the rest on the line as LoS Qty."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.tests.pos_fixtures import pos_profile_settings
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

	# Task 2

	def _cart(self, *lines):
		return [
			{"id": code, "quantity": qty, "los_qty": los, "uom": "Nos", "bundle_entries": []}
			for code, qty, los in lines
		]

	def _split(self, cart, enabled=1):
		from klik_pos.overrides.loss_of_sale import split_cart_items

		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=enabled):
			return split_cart_items(cart, frappe.get_doc("POS Profile", self.profile.name))

	def test_the_till_sells_what_is_in_stock(self):
		cart = self._cart((STOCKED, 16, 0))
		changes = self._split(cart)
		self.assertEqual((cart[0]["quantity"], cart[0]["los_qty"]), (10, 6))
		self.assertEqual(changes, [{"index": 0, "item_code": STOCKED, "quantity": 10, "los_qty": 6}])

	def test_with_loss_of_sale_off_nothing_changes(self):
		cart = self._cart((STOCKED, 16, 0), (STOCKED, 2, 3))
		self.assertEqual(self._split(cart, enabled=0), [])
		self.assertEqual([(i["quantity"], i["los_qty"]) for i in cart], [(16, 0), (2, 0)])

	def test_an_item_with_no_stock_stays_as_a_zero_line(self):
		cart = self._cart((STOCKED, 4, 0), (EMPTY, 6, 0))
		self._split(cart)
		self.assertEqual([(i["quantity"], i["los_qty"]) for i in cart], [(4, 0), (0, 6)])

	def test_a_sale_with_nothing_in_stock_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing on this sale is in stock"):
			self._split(self._cart((EMPTY, 6, 0)))

	def test_reserved_stock_is_not_offered(self):
		cart = self._cart((STOCKED, 16, 0))
		with patch(
			"klik_pos.api.sales_invoice.get_reserved_stock_map",
			return_value={(STOCKED, self.warehouse): 4},
		):
			self._split(cart)
		self.assertEqual((cart[0]["quantity"], cart[0]["los_qty"]), (6, 10))

	def test_splitting_twice_changes_nothing_the_second_time(self):
		cart = self._cart((STOCKED, 16, 0))
		self._split(cart)
		self.assertEqual(self._split(cart), [])

	# Task 3

	def _desk_invoice(self, *rows):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = self.customer
		invoice.company = self.company
		invoice.pos_profile = self.profile.name
		invoice.update_stock = 1
		for code, qty in rows:
			invoice.append("items", {"item_code": code, "qty": qty, "rate": 100, "warehouse": self.warehouse})
		invoice.insert(ignore_permissions=True)
		self.addCleanup(self._drop_invoice, invoice.name)
		return invoice

	def _ledger(self, invoice):
		return {
			row.item_code: row.actual_qty
			for row in frappe.get_all(
				"Stock Ledger Entry",
				filters={"voucher_no": invoice.name, "is_cancelled": 0},
				fields=["item_code", "actual_qty"],
			)
		}

	def test_desk_submit_sells_what_is_in_stock(self):
		invoice = self._desk_invoice((STOCKED, 16))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			invoice.submit()
		self.assertEqual((invoice.items[0].qty, invoice.items[0].custom_los_qty), (10, 6))
		self.assertEqual(self._ledger(invoice), {STOCKED: -10})

	def test_desk_zero_stock_line_is_kept_without_a_ledger_entry(self):
		invoice = self._desk_invoice((STOCKED, 4), (EMPTY, 6))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			invoice.submit()
		self.assertEqual([(row.qty, row.custom_los_qty) for row in invoice.items], [(4, 0), (0, 6)])
		self.assertEqual(self._ledger(invoice), {STOCKED: -4})

	def test_desk_with_loss_of_sale_off_still_refuses(self):
		invoice = self._desk_invoice((STOCKED, 16))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=0):
			with self.assertRaises(frappe.ValidationError):
				invoice.submit()

	def test_desk_sale_with_nothing_in_stock_is_refused(self):
		invoice = self._desk_invoice((EMPTY, 6))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			with self.assertRaisesRegex(frappe.ValidationError, "Nothing on this sale is in stock"):
				invoice.submit()

	def test_a_paid_invoice_is_never_shortened(self):
		from klik_pos.overrides.loss_of_sale import before_validate

		mode = frappe.db.get_value("Mode of Payment", {}, "name")
		sources = {
			"paid_amount": {"paid_amount": 50},
			"payment row": {"payments": [{"mode_of_payment": mode, "amount": 50}]},
			"loyalty": {"loyalty_amount": 50},
			"advance": {"total_advance": 50},
		}
		for label, money in sources.items():
			with self.subTest(label):
				invoice = frappe.new_doc("Sales Invoice")
				invoice.update({"customer": self.customer, "company": self.company, "pos_profile": self.profile.name})
				invoice.update_stock = 1
				invoice.update(money)
				invoice.append("items", {"item_code": STOCKED, "qty": 16, "rate": 100, "warehouse": self.warehouse})
				invoice._action = "submit"
				with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
					before_validate(invoice)
				self.assertEqual((invoice.items[0].qty, invoice.items[0].get("custom_los_qty") or 0), (16, 0))
