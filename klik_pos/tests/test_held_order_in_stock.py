"""A held order holds what the customer asked for (a Sales Order refuses qty-0 lines), so its
total counts lines that are out of stock. On a till that records Loss of Sale, the Held tab also
shows what the order would come to if checked out now: SO-00582 on dev2 held 10 belts at 100
with none in stock and a filter at 450, and read 1,450 where the till could sell 450.

"Checked out now" means at the cashier's own till: checkout splits by that till's setting and
warehouse, whichever till the order was held on."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_order import get_held_orders
from klik_pos.tests.pos_fixtures import pos_profile_settings
from klik_pos.tests.test_held_order_visibility import ITEM, _held_order


class TestHeldOrderInStockTotal(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.till = frappe.db.get_value("POS Profile", {"disabled": 0, "warehouse": ["is", "set"]}, "name")
		if not self.till:
			self.skipTest("no POS Profile on this site")
		self.order = _held_order()  # 1 x Consulting at 10
		frappe.db.set_value("Sales Order", self.order.name, "custom_pos_profile", self.till, update_modified=False)

	def _row(self, cashier_till_records_los, order_till_records_los=0, available=None):
		cashier_till = frappe.get_doc("POS Profile", self.till)
		cashier_till.custom_enable_loss_of_sale = cashier_till_records_los
		with (
			pos_profile_settings(self.till, custom_enable_loss_of_sale=order_till_records_los),
			patch("klik_pos.api.sales_order._active_till", return_value=cashier_till),
			# Consulting is a service: count it as stock Loss of Sale may shorten.
			patch("klik_pos.overrides.loss_of_sale._eligible_item_codes", side_effect=lambda codes: set(codes)),
			patch("klik_pos.overrides.loss_of_sale._available", return_value=available or {}),
		):
			result = get_held_orders(skip_opening_entry_filter=True, search=self.order.name, limit=200)
		self.assertTrue(result["success"], msg=result.get("error"))
		return next(row for row in result["data"] if row["name"] == self.order.name)

	def test_a_loss_of_sale_till_shows_what_is_in_stock(self):
		row = self._row(cashier_till_records_los=1)
		self.assertEqual(row["grand_total"], 10)
		self.assertEqual(row["in_stock_total"], 0)

	def test_other_tills_show_only_the_order_total(self):
		self.assertNotIn("in_stock_total", self._row(cashier_till_records_los=0))

	def test_the_cashier_s_till_decides_not_the_one_it_was_held_on(self):
		self.assertNotIn("in_stock_total", self._row(cashier_till_records_los=0, order_till_records_los=1))

	def test_stock_fills_the_lines_in_their_order(self):
		# 2 at 10 then 2 at 8, 3 in stock: 2 x 10 + 1 x 8 = 28 of 36, as checkout fills them.
		frappe.db.set_value("Sales Order Item", self.order.items[0].name, "qty", 2, update_modified=False)
		second = frappe.get_doc(
			{
				"doctype": "Sales Order Item", "parent": self.order.name, "parenttype": "Sales Order",
				"parentfield": "items", "idx": 2, "item_code": ITEM, "qty": 2, "rate": 8,
				"delivery_date": self.order.delivery_date, "warehouse": self.order.items[0].warehouse,
			}
		)
		second.db_insert()
		frappe.db.set_value("Sales Order", self.order.name, "grand_total", 36, update_modified=False)
		warehouse = frappe.db.get_value("POS Profile", self.till, "warehouse")
		row = self._row(cashier_till_records_los=1, available={(ITEM, warehouse): 3})
		self.assertEqual(row["in_stock_total"], 28)

	def test_a_failure_here_does_not_empty_the_held_tab(self):
		with patch("klik_pos.overrides.loss_of_sale.in_stock_total", side_effect=Exception("boom")):
			row = self._row(cashier_till_records_los=1)
		self.assertNotIn("in_stock_total", row)
