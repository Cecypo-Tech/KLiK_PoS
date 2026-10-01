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
