"""A site's own delivery-date stamp, written by klik only where the field exists.

klik stamps custom_delivery_date on every invoice and return it builds, but ships no such
field: on a site without one the value silently vanished on save. The stamp now goes only
where the site's Sales Invoice has the field; nothing in klik reads it back.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import _stamp_delivery_date, build_sales_invoice_doc

FIELD = "custom_delivery_date"


def _field_present(present):
	"""Fake the site's Sales Invoice meta having (or missing) the field."""
	meta = frappe.get_meta("Sales Invoice")
	has_field = meta.has_field
	return patch.object(meta, "has_field", side_effect=lambda f: present if f == FIELD else has_field(f))


class TestStampDeliveryDate(FrappeTestCase):
	def test_without_the_field_nothing_is_written(self):
		doc = frappe.new_doc("Sales Invoice")
		with _field_present(False):
			_stamp_delivery_date(doc)
		self.assertIsNone(doc.get(FIELD))

	def test_with_the_field_today_is_stamped(self):
		doc = frappe.new_doc("Sales Invoice")
		with _field_present(True):
			_stamp_delivery_date(doc)
		self.assertEqual(doc.get(FIELD), frappe.utils.nowdate())

	def test_a_rebuilt_documents_stamp_is_carried_not_renewed(self):
		doc = frappe.new_doc("Sales Invoice")
		with _field_present(True):
			_stamp_delivery_date(doc, "2026-01-01")
		self.assertEqual(doc.get(FIELD), "2026-01-01")


class TestBuiltInvoices(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_a_fieldless_site_gets_no_delivery_date(self):
		with _field_present(False):
			doc = build_sales_invoice_doc(
				"_Test Customer",
				[{"id": "_Test Item", "quantity": 1, "price": 100, "uom": "_Test UOM"}],
				0,
				None,
				None,
				"B2C",
				include_payments=False,
				is_credit_sale=False,
				due_date=frappe.utils.nowdate(),
				create_batch_and_serial_bundle=False,
			)
		self.assertIsNone(doc.get(FIELD))
