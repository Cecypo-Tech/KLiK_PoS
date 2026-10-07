"""A held order holds what the customer asked for (a Sales Order refuses qty-0 lines), so its
total counts lines that are out of stock. On a till that records Loss of Sale, the Held tab also
shows what the order would come to if checked out now: SO-00582 on dev2 held 10 belts at 100
with none in stock and a filter at 450, and read 1,450 where the till could sell 450."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_order import get_held_orders
from klik_pos.tests.pos_fixtures import pos_profile_settings
from klik_pos.tests.test_held_order_visibility import _held_order


class TestHeldOrderInStockTotal(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.till = frappe.db.get_value("POS Profile", {"disabled": 0}, "name")
		if not self.till:
			self.skipTest("no POS Profile on this site")
		self.order = _held_order()  # 1 x Consulting at 10
		frappe.db.set_value("Sales Order", self.order.name, "custom_pos_profile", self.till, update_modified=False)

	def _row(self, records_los):
		with (
			pos_profile_settings(self.till, custom_enable_loss_of_sale=records_los),
			# Consulting is a service: count it as stock Loss of Sale may shorten, with none held.
			patch("klik_pos.overrides.loss_of_sale._eligible_item_codes", side_effect=lambda codes: set(codes)),
			patch("klik_pos.overrides.loss_of_sale._available", return_value={}),
		):
			result = get_held_orders(skip_opening_entry_filter=True, search=self.order.name, limit=200)
		self.assertTrue(result["success"], msg=result.get("error"))
		return next(row for row in result["data"] if row["name"] == self.order.name)

	def test_a_loss_of_sale_till_shows_what_is_in_stock(self):
		row = self._row(records_los=1)
		self.assertEqual(row["grand_total"], 10)
		self.assertEqual(row["in_stock_total"], 0)

	def test_other_tills_show_only_the_order_total(self):
		self.assertNotIn("in_stock_total", self._row(records_los=0))
