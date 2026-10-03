"""Checkout with credit: validated before submit, applied right after, fail-safe.

The credit is not a payment row - paid_amount and every Mode of Payment total stay
untouched, so shift closing math cannot see it. A stale allocation (someone spent the
note between validation and apply) must not lose the sale: the invoice stays submitted,
the response carries a warning instead.

Runs through the real checkout, so it uses the site's current POS Profile (its company
and tax template decide the payable total - see pos_fixtures.payable_total) with a
customer and non-stock item of its own. Nothing commits; the test transaction takes
every document and counter with it.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api import customer_credit
from klik_pos.api import sales_invoice as si
from klik_pos.klik_pos.utils import get_current_pos_profile
from klik_pos.tests.credit_fixtures import make_credit_note
from klik_pos.tests.pos_fixtures import payable_total

CUSTOMER = "TEST-CREDIT-ROUTER-CUSTOMER"
ITEM = "TEST-CREDIT-ROUTER-ITEM"


def _ensure_customer():
	if frappe.db.exists("Customer", CUSTOMER):
		return
	frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": CUSTOMER,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		}
	).insert(ignore_permissions=True)


def _ensure_service_item():
	if frappe.db.exists("Item", ITEM):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM,
			"item_name": ITEM,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
		}
	).insert(ignore_permissions=True)


class TestCheckoutWithCredit(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = get_current_pos_profile().company
		_ensure_customer()
		_ensure_service_item()
		self.items = [{"id": ITEM, "quantity": 1, "price": 80, "uom": "Nos"}]
		self.total = flt(payable_total(CUSTOMER, self.items, None), 2)

	def _note(self, amount):
		return make_credit_note(CUSTOMER, self.company, amount, item=ITEM)

	def _checkout(self, credit_rows):
		# The SPA's payload shape: payment keys present (payment submission context),
		# nothing tendered, the credit rows carrying the value.
		data = {
			"customer": {"id": CUSTOMER},
			"items": self.items,
			"businessType": "B2C",
			"amountPaid": 0,
			"paymentMethods": [],
			"customerCredit": credit_rows,
		}
		return si.create_and_submit_invoice(data)

	def test_credit_covers_the_sale_and_leaves_no_payment_row(self):
		note = self._note(200)
		result = self._checkout([{"invoice": note.name, "amount": self.total}])
		self.assertTrue(result.get("success"), result)
		doc = frappe.get_doc("Sales Invoice", result["invoice_name"])
		self.assertEqual(flt(doc.outstanding_amount, 2), 0.0)
		self.assertEqual(flt(doc.paid_amount, 2), 0.0)
		self.assertFalse([p for p in doc.payments if flt(p.amount) > 0])
		self.assertEqual(flt(result["customer_credit"]["applied"], 2), self.total)

	def test_a_bad_allocation_blocks_before_submit(self):
		note = self._note(10)
		result = self._checkout([{"invoice": note.name, "amount": self.total}])
		self.assertFalse(result.get("success"), result)
		self.assertIn("holds", result.get("message") or "")

	def test_a_stale_allocation_fails_safe(self):
		note = self._note(200)
		with patch.object(si, "apply_customer_credit", side_effect=frappe.ValidationError("gone")):
			result = self._checkout([{"invoice": note.name, "amount": self.total}])
		self.assertTrue(result.get("success"), result)
		doc = frappe.get_doc("Sales Invoice", result["invoice_name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(flt(doc.outstanding_amount, 2), self.total)
		self.assertTrue(result["customer_credit"]["warning"])

	def test_the_cash_gate_lets_a_credit_covered_sale_through(self):
		"""Web-context submit with the v2 gate text: _klik_customer_credit exempts it."""
		note = self._note(200)
		frappe.local.request = frappe._dict(
			path="/api/method/klik_pos.api.sales_invoice.create_and_submit_invoice", method="POST"
		)
		try:
			result = self._checkout([{"invoice": note.name, "amount": self.total}])
		finally:
			frappe.local.request = None
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)

	def test_a_walkin_voucher_pays_with_its_original_number(self):
		note = self._note(200)
		with patch.object(customer_credit, "_is_walkin_customer", return_value=True):
			result = self._checkout(
				[{"invoice": note.name, "amount": self.total, "original": note.return_against}]
			)
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)

	def test_a_walkin_voucher_without_its_original_is_refused_at_checkout(self):
		note = self._note(200)
		with patch.object(customer_credit, "_is_walkin_customer", return_value=True):
			result = self._checkout([{"invoice": note.name, "amount": self.total}])
		self.assertFalse(result.get("success"), result)
		self.assertIn("original sale number", result.get("message") or "")
