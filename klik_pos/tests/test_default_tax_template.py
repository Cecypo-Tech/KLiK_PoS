"""A till that names no tax template is taxed with the company's default, the same way every
time.

Found in browser QA on dev: on a till with no Sales Taxes and Charges Template, a held order
was taxed on its first hold (1,110) and lost all its tax when held again (950). ERPNext's
set_taxes fills in the company's default template only on a *new* document, so the first
hold got it and the rebuild of an existing order did not. The same late default also skipped
klik's tax-inclusive handling: on a till that treats rates as tax-inclusive, a line keyed at
1,000 checked out at 1,160.

Now klik picks the default itself, before it builds the tax rows, so a new order, a re-held
order and an invoice all get the same template and the till's inclusive setting applies.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import _set_taxes_and_charges
from klik_pos.api.sales_order import create_held_order
from klik_pos.tests.test_held_order_replace import _payload

COMPANY = "Dev Co"


def _default_template():
	return frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": COMPANY, "is_default": 1, "disabled": 0}, "name"
	)


class TestDefaultTaxTemplate(FrappeTestCase):
	def setUp(self):
		self.default = _default_template()
		if not self.default:
			self.skipTest("no default Sales Taxes and Charges Template for Dev Co")

	def _till(self, inclusive):
		"""The caller's till with no template of its own, wherever the hold looks it up -
		the payload parser and the order builder each resolve it."""
		from klik_pos.api.sales_order import _get_active_pos_profile

		till = _get_active_pos_profile()
		if till.company != COMPANY:
			self.skipTest(f"active till is on {till.company}, not {COMPANY}")
		till.taxes_and_charges = None
		till.is_tax_included_in_basic_rate = 1 if inclusive else 0
		for target in (
			"klik_pos.api.sales_order._get_active_pos_profile",
			"klik_pos.api.sales_invoice.get_current_pos_profile",
		):
			patcher = patch(target, return_value=till)
			patcher.start()
			self.addCleanup(patcher.stop)
		return till

	def test_a_till_without_a_template_gets_the_company_default(self):
		doc = frappe.new_doc("Sales Order")
		doc.company = COMPANY

		_set_taxes_and_charges(doc, None, frappe._dict(taxes_and_charges=None))

		self.assertEqual(doc.taxes_and_charges, self.default)

	def test_a_template_chosen_at_checkout_or_on_the_till_still_wins(self):
		doc = frappe.new_doc("Sales Order")
		doc.company = COMPANY

		_set_taxes_and_charges(doc, "Chosen", frappe._dict(taxes_and_charges="Till's"))
		self.assertEqual(doc.taxes_and_charges, "Chosen")

		_set_taxes_and_charges(doc, None, frappe._dict(taxes_and_charges="Till's"))
		self.assertEqual(doc.taxes_and_charges, "Till's")

	def test_holding_again_keeps_the_tax(self):
		self._till(inclusive=False)
		first = create_held_order(_payload(qty=1))
		self.assertTrue(first["success"], msg=first.get("message"))
		taxed_once = frappe.db.get_value(
			"Sales Order", first["order_name"], ["total_taxes_and_charges", "taxes_and_charges"], as_dict=True
		)

		again = create_held_order(_payload(qty=1, held_order_id=first["order_name"]))
		self.assertTrue(again["success"], msg=again.get("message"))

		taxed_again = frappe.db.get_value(
			"Sales Order", first["order_name"], ["total_taxes_and_charges", "taxes_and_charges"], as_dict=True
		)
		self.assertGreater(flt(taxed_once.total_taxes_and_charges), 0)
		self.assertEqual(taxed_again.taxes_and_charges, self.default)
		self.assertEqual(flt(taxed_again.total_taxes_and_charges), flt(taxed_once.total_taxes_and_charges))

	def test_an_inclusive_till_includes_the_default_tax_in_the_price(self):
		self._till(inclusive=True)
		held = create_held_order(_payload(qty=1))
		self.assertTrue(held["success"], msg=held.get("message"))

		so = frappe.get_doc("Sales Order", held["order_name"])
		self.assertGreater(flt(so.total_taxes_and_charges), 0)
		# Keyed at 100 with tax included: the order totals 100, not 100 plus tax.
		self.assertEqual(flt(so.grand_total), 100.0)


TEST_TILL = "_Test POS Profile"  # on this bench: no template, rates include tax


class TestEveryReaderSeesTheSameTemplate(FrappeTestCase):
	"""The checkout's tax picker, the item grid's tax rows and the invoice all resolve the
	till's template the same way the order builder does."""

	def setUp(self):
		self.default = _default_template()
		if not self.default:
			self.skipTest("no default Sales Taxes and Charges Template for Dev Co")
		if not frappe.db.exists("POS Profile", TEST_TILL) or frappe.db.get_value(
			"POS Profile", TEST_TILL, "taxes_and_charges"
		):
			self.skipTest(f"{TEST_TILL} is missing or names its own template")
		self.till = frappe.get_doc("POS Profile", TEST_TILL)

	def test_the_resolver_falls_back_to_the_company_default(self):
		from klik_pos.api.tax import resolve_pos_tax_template

		self.assertEqual(resolve_pos_tax_template(self.till), self.default)
		self.assertEqual(resolve_pos_tax_template(frappe._dict(taxes_and_charges="Till's")), "Till's")
		self.assertIsNone(resolve_pos_tax_template(frappe._dict(taxes_and_charges=None, company=None)))

	def test_checkout_is_offered_the_template_the_server_will_use(self):
		from klik_pos.api.tax import get_sales_tax_categories

		with patch("klik_pos.api.tax.get_current_pos_profile", return_value=self.till):
			result = get_sales_tax_categories()

		self.assertEqual(result["default"], self.default)

	def test_the_item_grid_shows_the_template_s_tax_rows(self):
		from klik_pos.api.item.item_listing import _fetch_pos_sales_tax_rows

		self.assertTrue(_fetch_pos_sales_tax_rows(self.till))

	def test_an_invoice_keeps_the_template_its_rows_came_from(self):
		"""ERPNext's set_pos_fields copies the till's (empty) template onto a POS invoice,
		leaving tax rows with no template - which erpnext_express refuses."""
		from klik_pos.api.sales_invoice import _apply_pos_tax_treatment

		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": self.till.company,
				"customer": self.till.customer or "Walk In",
				"is_pos": 1,
				"pos_profile": TEST_TILL,
				"posting_date": frappe.utils.nowdate(),
			}
		)
		doc.append("items", {"item_code": "Consulting", "qty": 1, "rate": 100, "price_list_rate": 100})

		_apply_pos_tax_treatment(doc, self.till, None, [("Consulting", 100.0, 100.0)])

		self.assertEqual(doc.taxes_and_charges, self.default)
		self.assertTrue(doc.taxes)
		self.assertEqual(flt(doc.grand_total), 100.0)
