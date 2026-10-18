"""Walk-in Tax ID: an editable PIN field for walk-in buyers.

Sales Invoice/Sales Order.tax_id is fetched from the Customer on every draft save, so it
cannot hold a walk-in's PIN typed on the desk (and Quotation has no tax_id at all).
custom_walkin_tax_id holds it instead; a validate hook (which runs after the fetch) copies it
into tax_id, where KRA, print formats and the till already look.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import _apply_walkin_party_fields
from klik_pos.overrides.walkin_tax_id import sync_walkin_tax_id
from klik_pos.setup.walkin_fields import WALKIN_FIELDS, install_walkin_fields

PIN = "P051234567X"


def _doc(has, **values):
	doc = SimpleNamespace(**values)
	doc.meta = MagicMock()
	doc.meta.has_field.side_effect = lambda f: f in has
	return doc


class TestWalkinTaxIdSpec(FrappeTestCase):
	def test_the_field_set_includes_walkin_tax_id_after_the_phone(self):
		by_name = {f["fieldname"]: f for f in WALKIN_FIELDS}
		f = by_name["custom_walkin_tax_id"]
		self.assertEqual(f["fieldtype"], "Data")
		self.assertEqual(f["label"], "Walk-in Tax ID")
		self.assertEqual(f["insert_after"], "custom_walkin_phone")
		self.assertEqual(f["no_copy"], 0)  # carries Quotation -> Order -> Invoice


class TestSyncHook(FrappeTestCase):
	def test_copies_the_walkin_pin_into_tax_id_normalised(self):
		doc = _doc({"custom_walkin_tax_id", "tax_id"}, custom_walkin_tax_id=" p051234567x ", tax_id=None)
		sync_walkin_tax_id(doc)
		self.assertEqual(doc.custom_walkin_tax_id, PIN)
		self.assertEqual(doc.tax_id, PIN)

	def test_leaves_tax_id_alone_without_a_walkin_pin(self):
		doc = _doc({"custom_walkin_tax_id", "tax_id"}, custom_walkin_tax_id="", tax_id="A000000000B")
		sync_walkin_tax_id(doc)
		self.assertEqual(doc.tax_id, "A000000000B")

	def test_quotation_without_tax_id_only_normalises(self):
		doc = _doc({"custom_walkin_tax_id"}, custom_walkin_tax_id="p051234567x")
		sync_walkin_tax_id(doc)
		self.assertEqual(doc.custom_walkin_tax_id, PIN)
		self.assertFalse(hasattr(doc, "tax_id"))

	def test_no_op_where_the_field_is_not_installed(self):
		doc = _doc(set(), tax_id="A000000000B")
		sync_walkin_tax_id(doc)
		self.assertEqual(doc.tax_id, "A000000000B")


class TestTillFillsTheField(FrappeTestCase):
	FIELDS = {"custom_walkin_customer_name", "custom_walkin_phone", "custom_walkin_tax_id"}

	@patch("klik_pos.api.sales_invoice.frappe.db.get_value", return_value=1)
	def test_a_walkin_sale_gets_the_pin(self, _walkin):
		doc = _doc(self.FIELDS, customer="Walk In")
		_apply_walkin_party_fields(doc, walkin_name="Jane", walkin_tax_id=PIN)
		self.assertEqual(doc.custom_walkin_tax_id, PIN)

	@patch("klik_pos.api.sales_invoice.frappe.db.get_value", return_value=0)
	def test_a_named_customer_s_pin_stays_out_of_the_walkin_field(self, _walkin):
		doc = _doc(self.FIELDS, customer="Karibu Builders Ltd")
		_apply_walkin_party_fields(doc, walkin_tax_id=PIN)
		self.assertFalse(hasattr(doc, "custom_walkin_tax_id"))


class TestDeskSaveKeepsThePin(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_walkin_fields(["Sales Invoice"])

	def test_a_draft_save_keeps_tax_id_from_the_walkin_pin(self):
		self.assertFalse(frappe.db.get_value("Customer", "_Test Customer", "tax_id"))
		inv = create_sales_invoice(company="_Test Company", customer="_Test Customer", do_not_save=True)
		inv.custom_walkin_tax_id = PIN
		inv.insert(ignore_permissions=True)
		inv.save(ignore_permissions=True)  # a second draft save re-fetches tax_id from the Customer
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "tax_id"), PIN)


class TestPatch(FrappeTestCase):
	@patch("klik_pos.patches.v16_0.add_walkin_tax_id_field.install_walkin_fields")
	def test_adds_the_field_where_walkin_fields_are_installed(self, install):
		from klik_pos.patches.v16_0 import add_walkin_tax_id_field as p
		with patch.object(p.frappe.db, "exists", side_effect=lambda dt, f: f["dt"] in ("Sales Invoice", "Quotation")):
			p.execute()
		self.assertEqual(sorted(install.call_args[0][0]), ["Quotation", "Sales Invoice"])

	@patch("klik_pos.patches.v16_0.add_walkin_tax_id_field.install_walkin_fields")
	def test_does_nothing_on_a_site_without_walkin_fields(self, install):
		from klik_pos.patches.v16_0 import add_walkin_tax_id_field as p
		with patch.object(p.frappe.db, "exists", return_value=None):
			p.execute()
		install.assert_not_called()
