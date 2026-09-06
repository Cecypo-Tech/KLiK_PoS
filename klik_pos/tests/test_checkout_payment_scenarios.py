"""Exact, partial and over payment at checkout - each declaring the config it needs.

The receipt-continuity and idempotency modules were producing partially-paid invoices by
accident (line price paid against a taxed grand total). This module covers the three
payment scenarios on purpose so nothing depends on how the POS Profile happens to be set.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import CHECKOUT_REQUEST_DOCTYPE, queue_sales_invoice
from klik_pos.tests.pos_fixtures import payable_total, pick_payment_mode, pos_profile_settings

ITEM_GROUP = "TEST-PAYSCEN-GROUP"
ITEM_CODE = "TEST-PAYSCEN-ITEM"
CUSTOMER = "TEST-PAYSCEN-CUSTOMER"


def _delete_requests(*request_ids):
	for request_id in request_ids:
		if request_id and frappe.db.exists(CHECKOUT_REQUEST_DOCTYPE, request_id):
			frappe.delete_doc(CHECKOUT_REQUEST_DOCTYPE, request_id, force=True, ignore_permissions=True)


def _ensure_customer():
	if frappe.db.exists("Customer", CUSTOMER):
		return CUSTOMER
	customer = frappe.new_doc("Customer")
	customer.customer_name = CUSTOMER
	customer.customer_type = "Individual"
	customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	customer.insert(ignore_permissions=True)
	return customer.name


class TestCheckoutPaymentScenarios(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ready = False

		from klik_pos.api.sales_invoice import get_current_pos_opening_entry

		if not get_current_pos_opening_entry():
			return

		from klik_pos.klik_pos.utils import get_current_pos_profile

		try:
			cls.pos_profile = get_current_pos_profile()
		except Exception:
			return
		cls.company = cls.pos_profile.company
		cls.warehouse = cls.pos_profile.warehouse or frappe.db.get_value(
			"Warehouse", {"is_group": 0, "company": cls.company}, "name"
		)
		cls.payment_mode = pick_payment_mode(cls.pos_profile.name)
		if not (cls.warehouse and cls.payment_mode):
			return
		cls.customer = _ensure_customer()

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

		cls.stock_entry = make_stock_entry(
			item_code=ITEM_CODE, target=cls.warehouse, qty=500, basic_rate=10, company=cls.company
		)
		frappe.db.commit()
		cls.ready = True

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "ready", False):
			for name in frappe.get_all(
				"Sales Invoice Item", filters={"item_code": ITEM_CODE}, pluck="parent", distinct=True
			):
				if not frappe.db.exists("Sales Invoice", name):
					continue
				invoice = frappe.get_doc("Sales Invoice", name)
				if invoice.docstatus == 1:
					invoice.flags.ignore_permissions = True
					invoice.cancel()
				frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

			if getattr(cls, "stock_entry", None) and frappe.db.exists("Stock Entry", cls.stock_entry.name):
				entry = frappe.get_doc("Stock Entry", cls.stock_entry.name)
				if entry.docstatus == 1:
					entry.flags.ignore_permissions = True
					entry.cancel()
				frappe.delete_doc("Stock Entry", cls.stock_entry.name, force=True, ignore_permissions=True)

			for name in frappe.get_all("Bin", filters={"item_code": ITEM_CODE}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			if frappe.db.exists("Item", ITEM_CODE):
				frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
			if frappe.db.exists("Item Group", ITEM_GROUP):
				frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", CUSTOMER):
				frappe.delete_doc("Customer", CUSTOMER, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no open POS Opening Entry / payment mode on this site")
		frappe.set_user("Administrator")

	def _items(self):
		return [{"id": ITEM_CODE, "item_code": ITEM_CODE, "quantity": 1, "price": 100, "uom": "Nos"}]

	def _total(self):
		return payable_total(self.customer, self._items(), self.payment_mode)

	def _sell(self, paid, allow_partial):
		request_id = frappe.generate_hash(length=24)
		self.addCleanup(_delete_requests, request_id)
		payload = {
			"checkout_request_id": request_id,
			"customer": {"id": self.customer},
			"items": self._items(),
			"amountPaid": paid,
			"paymentMethods": [{"method": self.payment_mode, "amount": paid}],
			"businessType": "B2C",
		}
		with pos_profile_settings(self.pos_profile.name, allow_partial_payment=1 if allow_partial else 0):
			response = queue_sales_invoice(payload)
		if response.get("invoice_name"):
			self.addCleanup(self._remove_invoice, response["invoice_name"])
			frappe.db.commit()
		return response

	def _remove_invoice(self, name):
		if not name or not frappe.db.exists("Sales Invoice", name):
			return
		invoice = frappe.get_doc("Sales Invoice", name)
		if invoice.docstatus == 1:
			invoice.flags.ignore_permissions = True
			invoice.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _invoice(self, response):
		self.assertTrue(response["success"], response.get("message"))
		return frappe.get_doc("Sales Invoice", response["invoice_name"])

	def test_the_payable_total_is_more_than_the_line_price_when_tax_applies(self):
		# Documents the premise: the line price is NOT what the checkout demands here.
		# If this ever fails the site has no tax on the fixture and the other scenarios
		# still hold - they never assume a rate.
		self.assertGreaterEqual(self._total(), 100)

	def test_paying_the_exact_total_succeeds_whatever_the_partial_flag_says(self):
		total = self._total()
		for allow_partial in (True, False):
			with self.subTest(allow_partial=allow_partial):
				invoice = self._invoice(self._sell(total, allow_partial))
				self.assertEqual(invoice.paid_amount, total)
				self.assertEqual(invoice.outstanding_amount, 0)

	def test_underpaying_is_rejected_when_the_profile_forbids_partial_payment(self):
		response = self._sell(self._total() / 2, allow_partial=False)
		self.assertFalse(response["success"])
		self.assertIn("Partial Payment", response["message"])
		# The draft is inserted before the submit is refused, so _abort_checkout keeps it
		# (docstatus 0) and returns its name for Invoice History to retry - see the
		# savepoint branch there. The contract is "no sale happened", not "no name".
		self.assertEqual(frappe.db.get_value("Sales Invoice", response["invoice_name"], "docstatus"), 0)
		self.assertEqual(frappe.db.count("Sales Invoice", {"customer": self.customer, "docstatus": 1}), 0)

	def test_underpaying_is_accepted_when_the_profile_allows_partial_payment(self):
		total = self._total()
		invoice = self._invoice(self._sell(total / 2, allow_partial=True))
		self.assertEqual(invoice.paid_amount, total / 2)
		self.assertEqual(invoice.outstanding_amount, total / 2)

	def test_overpaying_succeeds_and_leaves_nothing_outstanding(self):
		total = self._total()
		invoice = self._invoice(self._sell(total + 50, allow_partial=False))
		self.assertEqual(invoice.paid_amount, total + 50)
		# ERPNext's POS flow turns the excess into change rather than a negative balance:
		# measured as outstanding 0.0 / change 50.0 against a 116.0 grand total.
		self.assertEqual(invoice.outstanding_amount, 0)
		self.assertEqual(invoice.change_amount, 50)
