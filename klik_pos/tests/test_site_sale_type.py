"""A site's own Cash/Credit sale-type field, filled by klik.

Some sites name Sales Invoices from a field of their own (Allparts: custom_sale_type,
Cash -> CS-, Credit -> INV-). The name is fixed at insert, before any payment reaches the
invoice, and a credit sale then looks like an M-Pesa draft - nothing paid on either. Only
klik knows the cashier chose Credit Sale, so where the site has the field klik fills it.
klik ships the field (Allparts' definition), so every site records the sale type.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.api.sales_invoice import _set_site_sale_type, build_sales_invoice_doc
from klik_pos.overrides.sales_invoice import require_payment_for_cash_sale, set_sale_type

FIELD = "custom_sale_type"
CUSTOMER = "_Test Customer"
ITEM = "_Test Item"


def _with_options(*options):
	"""Stand in for the site's field: adding a real Custom Field is DDL, which commits."""
	return patch.object(sales_invoice, "_site_sale_types", return_value=set(options))


def _build(is_credit_sale):
	return build_sales_invoice_doc(
		CUSTOMER,
		[{"id": ITEM, "quantity": 1, "price": 100, "uom": "_Test UOM"}],
		0,
		None,
		None,
		"B2C",
		include_payments=False,
		is_credit_sale=is_credit_sale,
		due_date=frappe.utils.nowdate(),
		create_batch_and_serial_bundle=False,
	)


class TestSetSiteSaleType(FrappeTestCase):
	def test_a_credit_sale_is_credit_and_anything_else_cash(self):
		with _with_options("Cash", "Credit"):
			credit, cash = frappe.new_doc("Sales Invoice"), frappe.new_doc("Sales Invoice")
			_set_site_sale_type(credit, is_credit_sale=True)
			_set_site_sale_type(cash, is_credit_sale=False)
		self.assertEqual((credit.get(FIELD), cash.get(FIELD)), ("Credit", "Cash"))

	def test_a_field_with_other_options_is_left_alone(self):
		doc = frappe.new_doc("Sales Invoice")
		before = doc.get(FIELD)  # the site field's default, or None where there is no field
		with _with_options("Retail", "Wholesale"):
			_set_site_sale_type(doc, is_credit_sale=True)
		self.assertEqual(doc.get(FIELD), before)

	def test_a_site_without_the_field_is_left_alone(self):
		# The site this runs on may well have the field (dev does); hide it from the meta.
		meta = frappe.get_meta("Sales Invoice")
		get_field = meta.get_field
		with patch.object(meta, "get_field", side_effect=lambda f: None if f == FIELD else get_field(f)):
			self.assertEqual(sales_invoice._site_sale_types(), set())
			doc = frappe.new_doc("Sales Invoice")
			before = doc.get(FIELD)
			_set_site_sale_type(doc, is_credit_sale=True)
		self.assertEqual(doc.get(FIELD), before)


class TestNewInvoices(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_a_credit_sale_due_today_is_credit(self):
		"""The case a due-date rule cannot tell from an M-Pesa draft."""
		with _with_options("Cash", "Credit"):
			self.assertEqual(_build(is_credit_sale=True).get(FIELD), "Credit")

	def test_a_cash_sale_or_an_mpesa_draft_is_cash(self):
		with _with_options("Cash", "Credit"):
			self.assertEqual(_build(is_credit_sale=False).get(FIELD), "Cash")

	def test_without_the_field_klik_sets_nothing(self):
		# Not marked Credit: klik left the field alone (the site's own default may still fill it).
		with _with_options():
			self.assertNotEqual(_build(is_credit_sale=True).get(FIELD), "Credit")


class TestAResavedDraftKeepsItsType(FrappeTestCase):
	"""The name was fixed when the draft was first saved; the type must keep matching it
	(and a site may mark the field Set Only Once)."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_finishing_a_cash_draft_on_credit_does_not_change_it(self):
		with _with_options("Cash", "Credit"):
			draft = _build(is_credit_sale=False)
			self.assertEqual(draft.get(FIELD), "Cash")
			sales_invoice._update_existing_draft_invoice(
				draft,
				CUSTOMER,
				[{"id": ITEM, "quantity": 1, "price": 100, "uom": "_Test UOM"}],
				0,
				None,
				None,
				"B2C",
				0.0,
				is_credit_sale=True,
				due_date=frappe.utils.nowdate(),
			)
		self.assertEqual(draft.get(FIELD), "Cash")


class TestReadingTheSiteField(FrappeTestCase):
	"""The option parsing itself, against a stub of the site's field (no DDL)."""

	def _options(self, field):
		meta = frappe.get_meta("Sales Invoice")
		with patch.object(meta, "get_field", side_effect=lambda f: field if f == FIELD else None):
			return sales_invoice._site_sale_types()

	def test_a_select_s_options_are_read_without_blanks(self):
		field = frappe._dict(fieldtype="Select", options="\nCash\n Credit \n")
		self.assertEqual(self._options(field), {"Cash", "Credit"})

	def test_a_field_that_is_not_a_select_is_ignored(self):
		self.assertEqual(self._options(frappe._dict(fieldtype="Data", options="Cash\nCredit")), set())


class TestAnMpesaDraftIsCash(FrappeTestCase):
	"""create_draft_invoice's draft collects M-Pesa money: Cash, even with Credit Sale ticked."""

	def test_a_draft_built_as_credit_is_marked_cash(self):
		unsaved = frappe.new_doc("Sales Invoice")
		# is_credit_sale (index 9) left ticked.
		parsed = (CUSTOMER, [], 0, [], None, "B2C", 0, 0, None, True, False, None, None, None, False, None)
		with (
			patch.object(sales_invoice, "parse_invoice_data", return_value=parsed),
			patch.object(sales_invoice, "build_sales_invoice_doc", return_value=unsaved),
			patch.object(sales_invoice, "validate_required_salesperson"),
			patch.object(sales_invoice, "_set_site_sale_type") as set_type,
			patch.object(unsaved, "insert", side_effect=frappe.ValidationError("stop before saving")),
		):
			sales_invoice.create_draft_invoice({})
		set_type.assert_called_once_with(unsaved, is_credit_sale=False)


class TestAnExtraFieldDoesNotCarryIt(FrappeTestCase):
	"""A till may list the site's field as an extra field; the re-save copy loop skips it."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_a_listed_field_is_not_copied_onto_the_draft(self):
		meta = frappe.get_meta("Sales Invoice")
		has_field = meta.has_field
		with (
			_with_options("Cash", "Credit"),
			patch.object(meta, "has_field", side_effect=lambda f: f == FIELD or has_field(f)),
			patch("klik_pos.api.pos_profile.get_configured_extra_fieldnames", return_value=[FIELD]),
		):
			draft = _build(is_credit_sale=False)
			sales_invoice._update_existing_draft_invoice(
				draft,
				CUSTOMER,
				[{"id": ITEM, "quantity": 1, "price": 100, "uom": "_Test UOM"}],
				0,
				None,
				None,
				"B2C",
				0.0,
				is_credit_sale=True,
				due_date=frappe.utils.nowdate(),
			)
		self.assertEqual(draft.get(FIELD), "Cash")


class TestSaleTypeFieldShipped(FrappeTestCase):
	def test_klik_ships_the_sale_type_field(self):
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Sales Invoice", "fieldname": FIELD},
			["module", "fieldtype", "options", "default", "reqd"],
			as_dict=True,
		)
		self.assertEqual(
			field,
			{"module": "KLiK PoS", "fieldtype": "Select", "options": "Cash\nCredit", "default": "Cash", "reqd": 1},
		)


def _invoice(**values):
	return frappe.get_doc({"doctype": "Sales Invoice", **values})


def _web_request():
	"""A desk/API submission; scripts, tests and background jobs have no request."""
	return patch.object(frappe.local, "request", frappe._dict(path="/api/method/x"), create=True)


class TestSetSaleType(FrappeTestCase):
	"""before_insert: every invoice gets a type; a return keeps its original's."""

	def test_a_blank_type_is_cash(self):
		doc = _invoice()
		doc.set(FIELD, None)
		set_sale_type(doc)
		self.assertEqual(doc.get(FIELD), "Cash")

	def test_a_chosen_type_stands(self):
		doc = _invoice(**{FIELD: "Credit"})
		set_sale_type(doc)
		self.assertEqual(doc.get(FIELD), "Credit")

	def test_a_return_takes_its_original_s_type(self):
		doc = _invoice(is_return=1, return_against="SINV-X", **{FIELD: "Cash"})
		with patch.object(frappe.db, "get_value", return_value="Credit"):
			set_sale_type(doc)
		self.assertEqual(doc.get(FIELD), "Credit")

	def test_a_return_against_an_untyped_original_is_cash(self):
		doc = _invoice(is_return=1, return_against="SINV-X", **{FIELD: "Credit"})
		with patch.object(frappe.db, "get_value", return_value=None):
			set_sale_type(doc)
		self.assertEqual(doc.get(FIELD), "Cash")


class TestCashSaleNeedsPayment(FrappeTestCase):
	"""before_submit: a Cash sale submitted from the desk or API is fully paid."""

	def test_an_unpaid_cash_sale_is_refused(self):
		doc = _invoice(outstanding_amount=100, **{FIELD: "Cash"})
		with _web_request(), self.assertRaises(frappe.ValidationError):
			require_payment_for_cash_sale(doc)

	def test_these_pass(self):
		cases = {
			"credit": _invoice(outstanding_amount=100, **{FIELD: "Credit"}),
			"paid": _invoice(outstanding_amount=0.004, **{FIELD: "Cash"}),
			"return": _invoice(outstanding_amount=-100, is_return=1, **{FIELD: "Cash"}),
			"consolidated": _invoice(outstanding_amount=100, is_consolidated=1, **{FIELD: "Cash"}),
		}
		with _web_request():
			for case, doc in cases.items():
				with self.subTest(case):
					require_payment_for_cash_sale(doc)

	def test_a_voucher_covering_the_balance_is_payment(self):
		"""A customer-credit voucher settles the sale right after submit (checkout's marker)."""
		doc = _invoice(outstanding_amount=100, **{FIELD: "Cash"})
		doc._klik_customer_credit = 100
		with _web_request():
			require_payment_for_cash_sale(doc)

	def test_a_voucher_short_of_the_balance_is_not(self):
		doc = _invoice(outstanding_amount=100, **{FIELD: "Cash"})
		doc._klik_customer_credit = 60
		with _web_request(), self.assertRaises(frappe.ValidationError):
			require_payment_for_cash_sale(doc)

	def test_no_request_is_not_enforced(self):
		doc = _invoice(outstanding_amount=100, **{FIELD: "Cash"})
		with patch.object(frappe.local, "request", None, create=True):
			require_payment_for_cash_sale(doc)
