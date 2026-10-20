"""The till's picked warehouse travels with each request, in the X-Klik-Warehouse header.

The picker only changed what the till showed: invoices, held orders, scans and batch picks
were all built from the POS Profile's own warehouse, so a cashier switched to B saw B's
stock and sold A's.
"""

from contextlib import contextmanager
from urllib.parse import quote

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from klik_pos.api.sales_invoice import _get_active_pos_profile
from klik_pos.klik_pos.utils import (
	WAREHOUSE_HEADER,
	checked_warehouse,
	get_current_pos_profile,
	get_current_pos_profile_lite,
)
from klik_pos.tests.pos_fixtures import open_own_shift, pos_profile_settings

TILL = "TEST-PICKED-WAREHOUSE-TILL"


@contextmanager
def picked(warehouse):
	"""As if the till sent `warehouse` in the header."""
	before = getattr(frappe.local, "request", None)
	# As the till sends it: URL-encoded, a header value being Latin-1 only.
	headers = {WAREHOUSE_HEADER: quote(warehouse)} if warehouse else {}
	frappe.local.request = Request(EnvironBuilder(path="/api/method/test", headers=headers).get_environ())
	try:
		yield
	finally:
		frappe.local.request = before


def other_warehouse(profile):
	"""A leaf, enabled warehouse of the till's company that is not its own."""
	return frappe.db.get_value(
		"Warehouse",
		{"company": profile.company, "is_group": 0, "disabled": 0, "name": ["!=", profile.warehouse]},
		"name",
	)


class TestPickedWarehouse(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ready = bool(
			open_own_shift(cls, TILL, prefer=lambda p: other_warehouse(frappe.get_doc("POS Profile", p)))
		)
		if cls.ready:
			cls.till = get_current_pos_profile()
			cls.own = cls.till.warehouse
			cls.other = other_warehouse(cls.till)
			cls.ready = bool(cls.own and cls.other)

	def setUp(self):
		if not self.ready:
			self.skipTest("no open shift with two warehouses on this site")
		frappe.set_user("Administrator")

	def test_every_resolver_hands_out_the_picked_warehouse(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(self.other):
			self.assertEqual(get_current_pos_profile().warehouse, self.other)
			self.assertEqual(_get_active_pos_profile().warehouse, self.other)
			self.assertEqual(get_current_pos_profile_lite(["warehouse"]).warehouse, self.other)

	def test_no_header_means_the_tills_own_warehouse(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(None):
			self.assertEqual(get_current_pos_profile().warehouse, self.own)

	def test_no_request_means_the_tills_own_warehouse(self):
		before = getattr(frappe.local, "request", None)
		frappe.local.request = None
		try:
			self.assertEqual(get_current_pos_profile().warehouse, self.own)
		finally:
			frappe.local.request = before

	def test_a_till_that_does_not_allow_switching_refuses(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=0), picked(self.other):
			with self.assertRaisesRegex(frappe.ValidationError, "does not allow"):
				get_current_pos_profile()

	def test_the_tills_own_warehouse_is_always_fine(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=0):
			self.assertIsNone(checked_warehouse(self.till, self.own))

	def test_a_group_warehouse_is_refused(self):
		group = frappe.db.get_value("Warehouse", {"company": self.till.company, "is_group": 1}, "name")
		with pos_profile_settings(self.till.name, allow_warehouse_change=1):
			self.till.allow_warehouse_change = 1
			with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
				checked_warehouse(self.till, group)

	def test_another_companys_warehouse_is_refused(self):
		foreign = frappe.db.get_value(
			"Warehouse", {"company": ["not in", [self.till.company, ""]], "is_group": 0}, "name"
		)
		if not foreign:
			self.skipTest("only one company with warehouses on this site")
		self.till.allow_warehouse_change = 1
		with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
			checked_warehouse(self.till, foreign)

	def test_a_warehouse_the_user_may_not_use_is_refused(self):
		user = "picked-warehouse@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Picked", "send_welcome_email": 0}).insert(ignore_permissions=True)
		perm = frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Warehouse", "for_value": self.own}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", user, force=True, ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User Permission", perm.name, force=True, ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		self.till.allow_warehouse_change = 1
		frappe.set_user(user)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
			checked_warehouse(self.till, self.other)

	def test_which_tills_work_is_visible_stays_on_the_tills_own_warehouse(self):
		from klik_pos.api.sales_invoice import _tills_sharing_warehouse

		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(self.other):
			switched = _tills_sharing_warehouse(get_current_pos_profile())
		self.assertEqual(sorted(switched), sorted(_tills_sharing_warehouse(self.till)))


ITEM = "TEST-PICKED-WH-ITEM"
BARCODE = "PICKEDWH0001"


class TestSalesFollowThePickedWarehouse(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		from klik_pos.tests.pos_fixtures import pick_payment_mode
		from klik_pos.tests.test_checkout_payment_scenarios import _ensure_customer

		cls.ready = bool(
			open_own_shift(cls, TILL, prefer=lambda p: other_warehouse(frappe.get_doc("POS Profile", p)))
		)
		if not cls.ready:
			return
		cls.till = get_current_pos_profile()
		cls.other = other_warehouse(cls.till)
		cls.mode = pick_payment_mode(cls.till.name)
		cls.ready = bool(cls.other and cls.mode)
		if not cls.ready:
			return
		cls.customer = _ensure_customer()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"stock_uom": "Nos",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"is_stock_item": 1,
					"is_sales_item": 1,
					"barcodes": [{"barcode": BARCODE}],
				}
			).insert(ignore_permissions=True)
		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		# Stock only in the picked warehouse: selling from the till's own would fail.
		cls.entry = make_stock_entry(
			item_code=ITEM, target=cls.other, qty=20, basic_rate=10, company=cls.till.company
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "ready", False):
			for name in frappe.get_all("Sales Invoice Item", {"item_code": ITEM}, pluck="parent", distinct=True):
				doc = frappe.get_doc("Sales Invoice", name)
				if doc.docstatus == 1:
					doc.flags.ignore_permissions = True
					doc.cancel()
				frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
			entry = frappe.get_doc("Stock Entry", cls.entry.name)
			entry.flags.ignore_permissions = True
			entry.cancel()
			frappe.delete_doc("Stock Entry", entry.name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Bin", {"item_code": ITEM}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			frappe.delete_doc("Item", ITEM, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		if not self.ready:
			self.skipTest("no open shift with two warehouses and a payment mode")
		frappe.set_user("Administrator")
		switching = pos_profile_settings(self.till.name, allow_warehouse_change=1, allow_partial_payment=1)
		switching.__enter__()
		self.addCleanup(switching.__exit__, None, None, None)

	def _items(self):
		return [{"id": ITEM, "item_code": ITEM, "quantity": 1, "price": 100, "uom": "Nos"}]

	def test_an_invoice_is_built_from_the_picked_warehouse(self):
		from klik_pos.api.sales_invoice import build_sales_invoice_doc

		with picked(self.other):
			doc = build_sales_invoice_doc(self.customer, self._items(), 0, None, self.mode, "B2C")
		self.assertEqual({row.warehouse for row in doc.items}, {self.other})

	def test_a_held_order_is_built_from_the_picked_warehouse(self):
		from klik_pos.api.sales_order import _build_sales_order_doc

		with picked(self.other):
			so = _build_sales_order_doc(self.customer, self._items(), None, {})
		self.assertEqual({row.warehouse for row in so.items}, {self.other})

	def test_a_sale_takes_its_stock_from_the_picked_warehouse(self):
		from klik_pos.api.sales_invoice import queue_sales_invoice
		from klik_pos.tests.test_checkout_payment_scenarios import _delete_requests

		request_id = frappe.generate_hash(length=24)
		self.addCleanup(_delete_requests, request_id)
		payload = {
			"checkout_request_id": request_id,
			"customer": {"id": self.customer},
			"items": self._items(),
			"amountPaid": 1000,
			"paymentMethods": [{"method": self.mode, "amount": 1000}],
			"businessType": "B2C",
		}
		with picked(self.other):
			response = queue_sales_invoice(payload)
		self.assertTrue(response["success"], response.get("message"))
		frappe.db.commit()
		ledger = frappe.get_all(
			"Stock Ledger Entry",
			{"voucher_no": response["invoice_name"], "is_cancelled": 0},
			pluck="warehouse",
		)
		self.assertEqual(set(ledger), {self.other})

	def test_a_scan_reports_the_picked_warehouses_stock(self):
		from klik_pos.api.item.item_search import get_item_by_identifier

		with picked(self.other):
			found = get_item_by_identifier(BARCODE)
		in_picked = frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": self.other}, "actual_qty")
		self.assertGreater(in_picked, 0)
		self.assertEqual(found.get("available"), in_picked, found)

	def test_the_stock_lookups_warehouse_argument_is_checked(self):
		from klik_pos.api.item.item_stock import get_items_stock_batch

		with pos_profile_settings(self.till.name, allow_warehouse_change=0), picked(None):
			with self.assertRaisesRegex(frappe.ValidationError, "does not allow"):
				get_items_stock_batch(ITEM, warehouse=self.other)

	def _payload(self):
		return {
			"customer": {"id": self.customer},
			"items": self._items(),
			"amountPaid": 1000,
			"paymentMethods": [{"method": self.mode, "amount": 1000}],
			"businessType": "B2C",
		}

	def test_a_draft_saved_then_submitted_with_the_cart_sells_from_the_picked_warehouse(self):
		# Both rebuild the lines and call set_missing_values, which would put them back on
		# the till's own warehouse.
		from klik_pos.api.sales_invoice import create_draft_invoice, submit_draft_invoice

		with picked(self.other):
			draft = create_draft_invoice(self._payload())
			self.assertTrue(draft["success"], draft.get("message"))
			name = draft["invoice_name"]
			self.assertEqual(
				set(frappe.get_all("Sales Invoice Item", {"parent": name}, pluck="warehouse")), {self.other}
			)
			# Saved again from the cart: the existing draft is rebuilt.
			again = create_draft_invoice({**self._payload(), "draft_invoice_id": name})
			self.assertTrue(again["success"], again.get("message"))
			self.assertEqual(
				set(frappe.get_all("Sales Invoice Item", {"parent": name}, pluck="warehouse")), {self.other}
			)
			submitted = submit_draft_invoice(name, data=self._payload())
		self.assertTrue(submitted["success"], submitted.get("message"))
		frappe.db.commit()
		ledger = frappe.get_all("Stock Ledger Entry", {"voucher_no": name, "is_cancelled": 0}, pluck="warehouse")
		self.assertEqual(set(ledger), {self.other})
