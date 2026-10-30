"""A till can refuse printing its held orders (draft Sales Orders) by any route:
print view, PDF, QZ. Off by default; a submitted order always prints."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.overrides.sales_order import refuse_printing_a_held_order


def _order(docstatus=0, held=1, till="T"):
	return frappe._dict(
		doctype="Sales Order",
		name="SO-1",
		docstatus=docstatus,
		custom_is_klik_held=held,
		custom_pos_profile=till,
	)


def _till_blocks(on):
	return patch.object(frappe.db, "get_value", return_value=on)


class TestHeldOrderPrintBlock(FrappeTestCase):
	def test_refuses_a_held_draft_when_the_till_blocks_it(self):
		with _till_blocks(1), self.assertRaises(frappe.PermissionError):
			refuse_printing_a_held_order(_order(), "before_print")

	def test_prints_when_the_till_allows_it(self):
		with _till_blocks(0):
			refuse_printing_a_held_order(_order(), "before_print")

	def test_a_submitted_or_unheld_order_always_prints(self):
		with _till_blocks(1):
			refuse_printing_a_held_order(_order(docstatus=1), "before_print")
			refuse_printing_a_held_order(_order(held=0), "before_print")
			refuse_printing_a_held_order(_order(till=None), "before_print")
