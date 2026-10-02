"""A site's own Cash/Credit sale-type field, filled by klik.

Some sites name Sales Invoices from a field of their own (Allparts: custom_sale_type,
Cash -> CS-, Credit -> INV-). The name is fixed at insert, before any payment reaches the
invoice, and a credit sale then looks like an M-Pesa draft - nothing paid on either. Only
klik knows the cashier chose Credit Sale, so where the site has the field klik fills it.
klik adds no field of its own: without one, nothing changes.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.api.sales_invoice import _set_site_sale_type, build_sales_invoice_doc

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
		with _with_options("Retail", "Wholesale"):
			_set_site_sale_type(doc, is_credit_sale=True)
		self.assertIsNone(doc.get(FIELD))

	def test_a_site_without_the_field_is_left_alone(self):
		self.assertFalse(frappe.get_meta("Sales Invoice").has_field(FIELD), "dev should not have the field")
		self.assertEqual(sales_invoice._site_sale_types(), set())
		doc = frappe.new_doc("Sales Invoice")
		_set_site_sale_type(doc, is_credit_sale=True)
		self.assertIsNone(doc.get(FIELD))


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

	def test_without_the_field_the_invoice_carries_none(self):
		self.assertIsNone(_build(is_credit_sale=True).get(FIELD))


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
