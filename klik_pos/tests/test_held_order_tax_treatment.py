"""A held Sales Order must be taxed exactly like the Sales Invoice checked out from the same
cart.

Production bug (found on an end-to-end run on dev): a cashier on a POS Profile with
``is_tax_included_in_basic_rate`` held a VAT-bearing item at 300, it was approved, and
checkout then failed - the held order's approved snapshot recorded ``base_net_rate: 300.0``
(price treated as tax-exclusive), while the invoice built from the same cart priced the line
at ``base_net_rate: 258.62`` (300 with 16% VAT backed out). ``uncovered_rows`` correctly
reported the row as no longer covered, since the two documents disagreed about the line's own
net rate.

Root cause: ``build_sales_invoice_doc`` applies the till's tax treatment (the taxes-and-charges
template, per-item tax rows, and - when the POS Profile calls for it - tax-inclusive pricing),
but ``_build_sales_order_doc`` / ``_rebuild_sales_order`` in ``sales_order.py`` only ever set
``taxes_and_charges``. A held order therefore priced every rate as tax-exclusive: its own
totals were wrong, the minimum-selling-price floor judged it on a different net than the
invoice would use, and an approved order's price snapshot could never cover its own checkout.

The fix moves the tax treatment into a shared ``_apply_pos_tax_treatment`` in
``sales_invoice.py`` that both builders call, in the same order, and both now resolve each
line's ``item_tax_template`` / ``item_tax_rate`` the same way the invoice does.
"""

from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from klik_pos.api.sales_invoice import build_sales_invoice_doc
from klik_pos.api.sales_order import (
	_build_sales_order_doc,
	checkout_held_order,
	create_held_order,
)
from klik_pos.tests.test_held_order_price_approval import ROLE, SettingsSnapshot
from klik_pos.tests.test_opening_conflict import _profile, _shift, _user

COMPANY = "Dev Co"
CUSTOMER = "_Test Customer"
CASHIER = "klik-tax-treatment-cashier@example.com"
ITEM = "_Klik Tax Treatment Item"

STATE_PENDING = "Price Approval Pending"


def _vat_sales_tax_template():
	"""The company's default Sales Taxes and Charges Template - same helper klik's own
	pos_fixtures.default_sales_tax_template uses, and the same pattern
	test_checkout_number_burn.py's fixtures follow.

	A dedicated Item Tax Template was tried first and rejected: on this site an item always
	also resolves a second, pre-existing default item tax rule (a "VAT - DC" account,
	included_in_print_rate 0) through ERPNext's own get_item_details/set_taxes item-tax-
	template resolution, regardless of what is attached to the item under test - the two
	compete and the dedicated template's row never survives into doc.taxes. The company's
	*default* Sales Taxes and Charges Template does not have this problem (it is the thing
	klik's own tax helpers are built to apply) and reproduces the production numbers exactly:
	300 tax-inclusive at 16% VAT backs out to a net rate of 258.62.
	"""
	return frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": COMPANY, "is_default": 1}, "name"
	)


def _ensure_item():
	"""A dedicated item with valuation_rate 400 (floor 440 at 10%) - the same numbers the
	production report used."""
	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM,
				"item_name": ITEM,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"allow_negative_stock": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.set_value(
		"Item", ITEM, {"valuation_rate": 400, "last_purchase_rate": 400, "allow_negative_stock": 1}
	)


class TestHeldOrderTaxTreatment(SettingsSnapshot, FrappeTestCase):
	"""Fixtures (item, tax template, POS Profile, shift) are created once for the whole
	class, not per test - see task-2-report.md's fix-round-2 section for why - and every
	committed record is cleaned up again in tearDownClass, whose leak guard asserts the POS
	Profile and open-shift counts it started with are what it ends with.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls._profiles_before = frappe.db.count("POS Profile", {"name": ["like", "_Test Opening Conflict %"]})
		cls._open_entries_before = frappe.db.count(
			"POS Opening Entry", {"user": CASHIER, "docstatus": 1, "status": "Open"}
		)

		cls.tax_template = _vat_sales_tax_template()
		if not cls.tax_template:
			raise __import__("unittest").SkipTest(
				"no default Sales Taxes and Charges Template for Dev Co on this site"
			)
		_ensure_item()

		if not frappe.get_meta("Sales Order").has_field("powerpack_price_breach"):
			cls.price_approval_available = False
		else:
			cls.price_approval_available = True
			from cecypo_powerpack import price_approval as pa
			from cecypo_powerpack.tests.test_price_approval import ensure_workflow_state_columns

			pa.setup_custom_fields()
			ensure_workflow_state_columns()
			if not frappe.db.exists("Role", ROLE):
				frappe.get_doc({"doctype": "Role", "role_name": ROLE}).insert()

		_user(CASHIER)
		user_doc = frappe.get_doc("User", CASHIER)
		if not any(row.role == "Sales User" for row in user_doc.roles):
			user_doc.append("roles", {"role": "Sales User"})
			user_doc.flags.ignore_permissions = True
			user_doc.save()

		cls.till = _profile()
		frappe.db.set_value(
			"POS Profile",
			cls.till,
			{
				"is_tax_included_in_basic_rate": 1,
				"allow_partial_payment": 1,
				"taxes_and_charges": cls.tax_template,
			},
		)
		cls.shift = _shift(cls.till, CASHIER)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")

		shift = getattr(cls, "shift", None)
		if shift and frappe.db.exists("POS Opening Entry", shift):
			doc = frappe.get_doc("POS Opening Entry", shift)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
			frappe.delete_doc("POS Opening Entry", shift, force=True, ignore_permissions=True)

		till = getattr(cls, "till", None)
		if till and frappe.db.exists("POS Profile", till):
			frappe.delete_doc("POS Profile", till, force=True, ignore_permissions=True)

		frappe.db.commit()

		profiles_after = frappe.db.count("POS Profile", {"name": ["like", "_Test Opening Conflict %"]})
		open_entries_after = frappe.db.count(
			"POS Opening Entry", {"user": CASHIER, "docstatus": 1, "status": "Open"}
		)
		if profiles_after != cls._profiles_before or open_entries_after != cls._open_entries_before:
			raise AssertionError(
				"TestHeldOrderTaxTreatment leaked committed data: "
				f"POS Profile count {cls._profiles_before} -> {profiles_after}, "
				f"open POS Opening Entry count for {CASHIER} "
				f"{cls._open_entries_before} -> {open_entries_after}"
			)

		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Selling Settings", "validate_selling_price", 0)
		frappe.flags.powerpack_test_min_selling_price = True

		emails = patch(
			"frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email",
			new=lambda doc, transitions: None,
		)
		emails.start()
		self.addCleanup(emails.stop)

		if self.price_approval_available:
			self._configure(msp_approval_sales_order=1, msp_approval_sales_invoice=1)

		frappe.set_user(CASHIER)

	def tearDown(self):
		frappe.flags.powerpack_test_min_selling_price = False
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if self.price_approval_available:
			from cecypo_powerpack import price_approval as pa

			for dt in pa.APPROVAL_DOCTYPES:
				frappe.clear_cache(doctype=dt)
			frappe.clear_cache(doctype="PowerPack Settings")

	def _configure(self, **flags):
		s = frappe.get_single("PowerPack Settings")
		s.enable_min_selling_price = 1
		s.min_selling_price_default_basis = "Valuation Rate"
		s.min_selling_price_default_percent = 10
		s.min_selling_price_whole_sale = 0
		s.min_selling_price_override_role = ROLE
		s.set("min_selling_price_rules", [])
		for f in (
			"msp_approval_quotation",
			"msp_approval_sales_order",
			"msp_approval_sales_invoice",
			"msp_approval_delivery_note",
		):
			s.set(f, flags.get(f, 0))
		s.save()
		frappe.clear_cache(doctype="PowerPack Settings")
		return s

	# ---- helpers ------------------------------------------------------------------------

	def _items(self, rate=300, qty=1):
		# No item_tax_template here: the till's own default Sales Taxes and Charges
		# Template (set on cls.till, and read by _set_taxes_and_charges when the caller
		# passes no explicit sales_and_tax_charges) is what carries the 16% VAT.
		return [
			{
				"id": ITEM,
				"item_code": ITEM,
				"quantity": qty,
				"price": rate,
				"uom": "Nos",
			}
		]

	def _hold(self, rate=300, qty=1, held_order_id=None):
		payload = {
			"customer": {"id": CUSTOMER},
			"items": self._items(rate=rate, qty=qty),
			"status": "held",
		}
		if held_order_id:
			payload["held_order_id"] = held_order_id
		return create_held_order(payload)

	def _checkout_payload(self, rate=300, qty=1, request_id=None):
		return {
			"customer": {"id": CUSTOMER},
			"items": self._items(rate=rate, qty=qty),
			"isCreditSale": True,
			"dueDate": add_days(nowdate(), 7),
			"checkout_request_id": request_id or frappe.generate_hash(length=24),
			"businessType": "B2C",
		}

	# ---- 1: parity between the held order and the invoice built from the same cart ------

	def test_held_order_and_invoice_agree_on_net_and_totals(self):
		items = self._items(rate=300)

		so = _build_sales_order_doc(CUSTOMER, items, None, {})
		invoice = build_sales_invoice_doc(
			CUSTOMER, items, 0, None, None, "B2C", include_payments=False
		)

		self.assertEqual(len(so.items), 1)
		self.assertEqual(len(invoice.items), 1)
		# 300 tax-inclusive at 16% VAT backs out to a net rate of 258.62 - the exact
		# production numbers, not just "some number both agree on".
		self.assertAlmostEqual(flt(so.items[0].net_rate), 258.62, places=2)
		self.assertAlmostEqual(flt(so.items[0].net_rate), flt(invoice.items[0].net_rate), places=2)
		self.assertAlmostEqual(flt(so.items[0].net_amount), flt(invoice.items[0].net_amount), places=2)
		self.assertAlmostEqual(flt(so.net_total), flt(invoice.net_total), places=2)
		self.assertAlmostEqual(flt(so.grand_total), flt(invoice.grand_total), places=2)

	# ---- 2: the end-to-end failure, as a test --------------------------------------------

	def test_approved_held_order_checks_out_despite_tax_inclusive_pricing(self):
		if not self.price_approval_available:
			self.skipTest("cecypo_powerpack price-approval fields are not installed")

		# The recommended till setup (Sales Order routed, Sales Invoice not - see
		# test_held_order_price_approval.py's test 11): with invoice routing off, an
		# unmatched net rate hits cecypo_powerpack's own floor hard-block directly at
		# doc.insert() ("Net selling rate should be at least ...") instead of klik's own
		# "need approval" wording - this is the exact message the production report quoted.
		frappe.set_user("Administrator")
		self._configure(msp_approval_sales_order=1, msp_approval_sales_invoice=0)
		frappe.set_user(CASHIER)
		try:
			held = self._hold(rate=300)
			self.assertTrue(held["success"], held.get("message"))
			self.assertTrue(held["approval_requested"], held)
			self.assertEqual(held["approval_state"], STATE_PENDING)
			order_id = held["order_name"]
			self.assertEqual(
				frappe.db.get_value("Sales Order", order_id, "workflow_state"), STATE_PENDING
			)

			frappe.set_user("Administrator")
			so = frappe.get_doc("Sales Order", order_id)
			apply_workflow(so, "Approve")
			frappe.set_user(CASHIER)

			result = checkout_held_order(order_id, self._checkout_payload(rate=300))

			self.assertTrue(result["success"], result.get("message"))
			invoice = frappe.db.get_value(
				"Sales Invoice",
				result["invoice_name"],
				["powerpack_source_order", "powerpack_price_approved_rows", "docstatus"],
				as_dict=True,
			)
			self.assertEqual(invoice.powerpack_source_order, order_id)
			self.assertTrue(invoice.powerpack_price_approved_rows)
			self.assertEqual(invoice.docstatus, 1)
		finally:
			frappe.set_user("Administrator")
			self._configure(msp_approval_sales_order=1, msp_approval_sales_invoice=1)
			frappe.set_user(CASHIER)

	# ---- 3: re-holding must replace tax rows, not append to them ------------------------

	def test_re_holding_does_not_duplicate_tax_rows(self):
		# Well above the floor (440): this test is about tax rows, not price approval.
		first = self._hold(rate=1000)
		self.assertTrue(first["success"], first.get("message"))
		order_id = first["order_name"]

		so = frappe.get_doc("Sales Order", order_id)
		first_tax_row_count = len(so.taxes)
		self.assertGreater(first_tax_row_count, 0)

		second = self._hold(rate=1000, held_order_id=order_id)
		self.assertTrue(second["success"], second.get("message"))
		self.assertEqual(second["order_name"], order_id)

		so = frappe.get_doc("Sales Order", order_id)
		self.assertEqual(len(so.taxes), first_tax_row_count)
