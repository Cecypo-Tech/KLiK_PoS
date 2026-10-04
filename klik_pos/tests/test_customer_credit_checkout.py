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
from klik_pos.tests.pos_fixtures import payable_total, pick_payment_mode

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


def _totals(items):
	"""(grand_total, rounded_total) the checkout builds for `items`: the build
	pos_fixtures.payable_total runs, keeping both figures instead of the payable alone."""
	doc = si.build_sales_invoice_doc(CUSTOMER, items, 0, None, None, "B2C", include_payments=False)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	return flt(doc.grand_total, 2), flt(doc.rounded_total, 2)


def _ensure_open_shift(profile):
	"""Checkout refuses a till with no shift open today. Open one inside the test
	transaction when the site has none, so these tests do not depend on a live shift."""
	if frappe.get_all(
		"POS Opening Entry", filters={"pos_profile": profile.name, "docstatus": 1, "status": "Open"}
	):
		return
	entry = frappe.new_doc("POS Opening Entry")
	entry.period_start_date = frappe.utils.now()
	entry.posting_date = frappe.utils.nowdate()
	entry.company = profile.company
	entry.pos_profile = profile.name
	entry.user = "Administrator"
	entry.append(
		"balance_details",
		{
			"mode_of_payment": pick_payment_mode(profile.name),
			"opening_amount": 0,
			"custom_variance_reason": "test fixture: shift opened with an empty drawer",
		},
	)
	entry.insert(ignore_permissions=True)
	entry.submit()


class TestCheckoutWithCredit(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		profile = get_current_pos_profile()
		self.company = profile.company
		_ensure_open_shift(profile)
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

	def _no_partial_payment(self):
		"""A till that refuses part payment and credit sales: only a fully paid sale submits."""
		name = get_current_pos_profile().name
		fields = ["allow_partial_payment", "custom_allow_credit_sales_as_pos"]
		before = frappe.db.get_value("POS Profile", name, fields, as_dict=True)

		def restore():
			frappe.db.set_value("POS Profile", name, before)
			frappe.clear_document_cache("POS Profile", name)

		self.addCleanup(restore)
		frappe.db.set_value("POS Profile", name, dict.fromkeys(fields, 0))
		frappe.clear_document_cache("POS Profile", name)

	def test_a_voucher_pays_the_whole_sale_on_a_till_without_part_payment(self):
		self._no_partial_payment()
		note = self._note(200)
		result = self._checkout([{"invoice": note.name, "amount": self.total}])
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)

	def test_a_queued_voucher_sale_submits_on_a_till_without_part_payment(self):
		"""The worker loads the draft afresh, so the voucher it was handed must count as paid."""
		self._queued_voucher_sale("B2C")

	def test_a_queued_voucher_sale_to_a_business_customer_submits(self):
		"""A B2B sale (or a company customer on a B2B & B2C till) with no cash is not a POS
		sale when ERPNext fills in the till's payment modes, so it got none; made a POS sale
		afterwards with no payment row, ERPNext refused it at submit ("At least one mode of
		payment is required for POS invoice.")."""
		self._queued_voucher_sale("B2B")

	def test_a_voucher_sale_to_a_business_customer_submits_directly(self):
		self._no_partial_payment()
		note = self._note(200)
		result = si.create_and_submit_invoice(
			{
				"customer": {"id": CUSTOMER},
				"items": self.items,
				"businessType": "B2B",
				"amountPaid": 0,
				"paymentMethods": [],
				"customerCredit": [{"invoice": note.name, "amount": self.total}],
			}
		)
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)

	def _queued_voucher_sale(self, business_type):
		self._no_partial_payment()
		note = self._note(200)
		rows = [{"invoice": note.name, "amount": self.total}]
		with patch.object(si.frappe, "enqueue"):
			queued = si.create_and_submit_invoice(
				{
					"customer": {"id": CUSTOMER},
					"items": self.items,
					"businessType": business_type,
					"amountPaid": 0,
					"paymentMethods": [],
					"customerCredit": rows,
					"enable_background_invoice_submission": 1,
				}
			)
		self.assertTrue(queued.get("success"), queued)
		result = si.process_queued_sales_invoice(queued["invoice_name"], customer_credit=rows)
		self.assertTrue(result.get("success"), result)
		doc = frappe.get_doc("Sales Invoice", queued["invoice_name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(flt(doc.outstanding_amount, 2), 0.0)

	def test_a_voucher_short_of_the_sale_is_still_refused_without_part_payment(self):
		self._no_partial_payment()
		note = self._note(200)
		result = self._checkout([{"invoice": note.name, "amount": flt(self.total - 10, 2)}])
		self.assertFalse(result.get("success"), result)
		self.assertIn("Partial Payment", result.get("message") or "")

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

	def _sale_ending_in(self, cents):
		"""A sale whose grand total ends in `cents` hundredths (60 rounds up, 40 down),
		whatever tax the site's template adds: the price is scaled by what the checkout
		makes of 100. Returns its (grand_total, rounded_total) for the caller's premise."""
		grand_of_100, _ = _totals([{"id": ITEM, "quantity": 1, "price": 100, "uom": "Nos"}])
		price = flt((450 + cents / 100) * 100 / grand_of_100, 2)
		self.items = [{"id": ITEM, "quantity": 1, "price": price, "uom": "Nos"}]
		return _totals(self.items)

	def test_a_voucher_pays_a_total_that_rounds_up(self):
		"""The till caps a voucher at the rounded total, and the invoice settles at it."""
		grand, rounded = self._sale_ending_in(60)
		self.assertGreater(rounded, grand, f"premise: {grand} should round up, got {rounded}")
		note = self._note(600)
		result = self._checkout([{"invoice": note.name, "amount": rounded}])
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)
		self.assertEqual(flt(result["customer_credit"]["applied"], 2), rounded)

	def test_a_voucher_pays_a_total_that_rounds_down_through_the_cash_gate(self):
		"""Web-context submit: credit equal to the rounded total covers the sale, so the
		cash gate's marker is set though the unrounded grand total is a few cents more."""
		grand, rounded = self._sale_ending_in(40)
		self.assertTrue(0 < rounded < grand, f"premise: {grand} should round down, got {rounded}")
		note = self._note(600)
		frappe.local.request = frappe._dict(
			path="/api/method/klik_pos.api.sales_invoice.create_and_submit_invoice", method="POST"
		)
		try:
			result = self._checkout([{"invoice": note.name, "amount": rounded}])
		finally:
			frappe.local.request = None
		self.assertTrue(result.get("success"), result)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", result["invoice_name"], "outstanding_amount"), 2),
			0.0,
		)
