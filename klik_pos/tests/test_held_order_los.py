"""A held order at a Loss of Sale till keeps the cart's split: SAL-ORD-2026-00121 asked for 100
F049 with 75 in stock, and printed 100 because holding folded the 25 back into qty. It now holds
qty 75 + LoS 25, so its print and totals are for what is in stock. Reopening it asks for the
full 100 again and splits it against the stock at that till now - stock may have come in, or
more been sold, since it was held."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.overrides import loss_of_sale
from klik_pos.tests.test_held_order_visibility import COMPANY, CUSTOMER, ITEM

WAREHOUSE = "Stores - DC"


def _till(los):
	return frappe._dict({"name": "_Test Till", "warehouse": WAREHOUSE, "custom_enable_loss_of_sale": los})


class TestHoldingKeepsTheSplit(FrappeTestCase):
	def _row(self, till, item):
		with patch.object(sales_order, "_resolve_item_tax_details_for_line", return_value=(None, None)):
			return sales_order._so_item_row(frappe._dict(), till, item, WAREHOUSE)

	def test_a_loss_of_sale_till_holds_what_is_in_stock(self):
		row = self._row(_till(1), {"id": ITEM, "quantity": 75, "los_qty": 25})
		self.assertEqual((row["qty"], row["custom_los_qty"]), (75, 25))

	def test_a_line_with_nothing_in_stock_holds_qty_0(self):
		row = self._row(_till(1), {"id": ITEM, "quantity": 0, "los_qty": 10})
		self.assertEqual((row["qty"], row["custom_los_qty"]), (0, 10))

	def test_other_tills_hold_what_was_asked_for(self):
		row = self._row(_till(0), {"id": ITEM, "quantity": 75, "los_qty": 25})
		self.assertEqual((row["qty"], row["custom_los_qty"]), (100, 0))

	def test_an_order_with_a_loss_of_sale_line_at_qty_0_may_be_saved(self):
		self.assertIn(
			"klik_pos.overrides.loss_of_sale.before_validate_order",
			frappe.get_hooks("doc_events")["Sales Order"]["before_validate"],
		)
		so = frappe.new_doc("Sales Order")
		so.append("items", {"item_code": ITEM, "qty": 0, "custom_los_qty": 10})
		loss_of_sale.before_validate_order(so)
		self.assertTrue(so.flags.allow_zero_qty)

	def test_the_print_and_total_are_for_the_held_qty(self):
		so = frappe.new_doc("Sales Order")
		so.update({"customer": CUSTOMER, "company": COMPANY, "transaction_date": frappe.utils.nowdate(),
			"delivery_date": frappe.utils.nowdate()})
		so.append("items", {"item_code": ITEM, "qty": 75, "custom_los_qty": 25, "rate": 10})
		so.append("items", {"item_code": ITEM, "qty": 0, "custom_los_qty": 5, "rate": 10})
		so.run_method("before_validate")
		so.run_method("validate")
		self.assertEqual(so.total, 750)


class TestReopeningSplitsAgain(FrappeTestCase):
	def _reopen(self, till, held_qty, los_qty, in_stock):
		items = [{"id": ITEM, "quantity": held_qty, "los_qty": los_qty, "uom": None}]
		with (
			patch.object(loss_of_sale, "_eligible_item_codes", side_effect=lambda codes: set(codes)),
			patch.object(loss_of_sale, "_available", return_value={(ITEM, WAREHOUSE): in_stock}),
		):
			loss_of_sale.split_held_items(items, till)
		return items[0]["quantity"], items[0]["los_qty"]

	def test_stock_that_came_in_fills_the_line(self):
		self.assertEqual(self._reopen(_till(1), 75, 25, in_stock=120), (100, 0))

	def test_stock_sold_since_shortens_the_line(self):
		self.assertEqual(self._reopen(_till(1), 75, 25, in_stock=40), (40, 60))

	def test_nothing_in_stock_still_opens(self):
		self.assertEqual(self._reopen(_till(1), 75, 25, in_stock=0), (0, 100))

	def test_a_till_without_loss_of_sale_opens_the_full_ask(self):
		self.assertEqual(self._reopen(_till(0), 75, 25, in_stock=40), (100, 0))

	def test_no_till_opens_the_full_ask(self):
		self.assertEqual(self._reopen(None, 75, 25, in_stock=40), (100, 0))

	def test_the_details_carry_the_new_split(self):
		so = frappe.new_doc("Sales Order")
		so.update({"name": "SO-LOS-TEST", "customer": CUSTOMER, "currency": "KES"})
		so.append("items", {"item_code": ITEM, "qty": 75, "custom_los_qty": 25, "rate": 10, "uom": "Nos"})
		real_get_doc = frappe.get_doc
		with (
			patch("frappe.get_doc", side_effect=lambda *a, **k: so if a[:2] == ("Sales Order", "SO-LOS-TEST") else real_get_doc(*a, **k)),
			patch.object(sales_order, "_assert_held_order_access"),
			patch.object(sales_order, "_active_till", return_value=_till(1)),
			patch.object(loss_of_sale, "_eligible_item_codes", side_effect=lambda codes: set(codes)),
			patch.object(loss_of_sale, "_available", return_value={(ITEM, WAREHOUSE): 40}),
		):
			result = sales_order.get_held_order_details("SO-LOS-TEST")
		self.assertTrue(result["success"], msg=result)
		self.assertEqual((result["items"][0]["quantity"], result["items"][0]["los_qty"]), (40, 60))

	def test_an_mpesa_order_opens_as_held(self):
		"""Its push was for the held total: re-splitting would sell less than was paid."""
		so = frappe.new_doc("Sales Order")
		so.update({"name": "SO-LOS-MPESA", "customer": CUSTOMER, "currency": "KES", "custom_klik_mpesa_order": 1})
		so.append("items", {"item_code": ITEM, "qty": 100, "rate": 10, "uom": "Nos"})
		real_get_doc = frappe.get_doc
		with (
			patch("frappe.get_doc", side_effect=lambda *a, **k: so if a[:2] == ("Sales Order", "SO-LOS-MPESA") else real_get_doc(*a, **k)),
			patch.object(sales_order, "_assert_held_order_access"),
			patch.object(sales_order, "_active_till", return_value=_till(1)),
			patch.object(sales_order, "_mpesa_fields", return_value={}),
			patch.object(loss_of_sale, "_eligible_item_codes", side_effect=lambda codes: set(codes)),
			patch.object(loss_of_sale, "_available", return_value={(ITEM, WAREHOUSE): 40}),
		):
			result = sales_order.get_held_order_details("SO-LOS-MPESA")
		self.assertTrue(result["success"], msg=result)
		self.assertEqual((result["items"][0]["quantity"], result["items"][0]["los_qty"]), (100, 0))


class TestTheHeldTabTotal(FrappeTestCase):
	def test_sales_order_item_has_the_los_field(self):
		self.assertTrue(frappe.get_meta("Sales Order Item").has_field("custom_los_qty"))

	def test_the_in_stock_total_scales_from_what_is_held(self):
		# Held 75 + LoS 25 at 10 (total 750); 100 in stock now: checkout would sell 1,000.
		key = (ITEM, WAREHOUSE)
		line = {"key": key, "requested": 100, "held": 75, "factor": 1, "rate": 10, "eligible": True}
		self.assertEqual(loss_of_sale.in_stock_total(750, [line], {key: 100}), 1000)
