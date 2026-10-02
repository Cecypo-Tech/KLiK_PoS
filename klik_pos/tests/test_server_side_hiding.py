"""C3: what a till hides on screen, the server does not send.

- 'Hide Cost Price' (restrict_cost_visibility_in_tooltip): the item details endpoint leaves
  out every valuation, stock value, cost and margin figure. The list view already did.
- 'Hide Expected Amount' (custom_hide_expected_amount): the payment summary leaves out the
  shift's takings, as closing_summary does. The float the cashier entered stays.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_details
from klik_pos.api.item.item_details import _without_cost
from klik_pos.tests.test_allow_closing_shift import CASHIER_ROLES, FIELD as ALLOW_CLOSING, ClosingCase
from klik_pos.tests.test_shared_shift import OPENER


def _details():
	return {
		"item_name": "Rope",
		"standard_rate": 120.0,
		"valuation_rate": 80.0,
		"global_stock_total": {"total_qty": 10.0, "total_value": 800.0, "avg_valuation_rate": 80.0},
		"total_bal_qty": 10.0,
		"total_bal_val": 800.0,
		"price_lists": [
			{"price_list": "Retail", "rate": 120.0, "cost": 80.0, "margin": 40.0, "margin_pct": 50.0}
		],
		"batches": [
			{
				"batch_id": "B1",
				"qty": 4.0,
				"val": 320.0,
				"val_rate": 80.0,
				"serials": [{"serial_no": "S1", "warehouse": "W", "val_rate": 80.0}],
			}
		],
		"serials": [{"serial_no": "S2", "warehouse": "W", "val_rate": 80.0}],
		"warehouse_stock": [{"warehouse": "W", "bal_qty": 10.0, "bal_val": 800.0, "val_rate": 80.0}],
	}


class TestCostIsNotSent(FrappeTestCase):
	def test_every_cost_figure_is_left_out(self):
		hidden = _without_cost(_details())
		self.assertEqual(hidden["valuation_rate"], 0)
		self.assertEqual(hidden["total_bal_val"], 0)
		self.assertEqual(hidden["global_stock_total"], {"total_qty": 10.0, "total_value": 0, "avg_valuation_rate": 0})
		self.assertEqual(
			hidden["price_lists"], [{"price_list": "Retail", "rate": 120.0, "cost": 0, "margin": 0, "margin_pct": 0}]
		)
		batch = hidden["batches"][0]
		self.assertEqual((batch["qty"], batch["val"], batch["val_rate"], batch["serials"][0]["val_rate"]), (4.0, 0, 0, 0))
		self.assertEqual(hidden["serials"][0]["val_rate"], 0)
		self.assertEqual(hidden["warehouse_stock"], [{"warehouse": "W", "bal_qty": 10.0, "bal_val": 0, "val_rate": 0}])

	def test_selling_figures_and_quantities_stay(self):
		hidden = _without_cost(_details())
		self.assertEqual((hidden["item_name"], hidden["standard_rate"], hidden["total_bal_qty"]), ("Rope", 120.0, 10.0))
		self.assertEqual(hidden["price_lists"][0]["rate"], 120.0)

	def test_the_endpoint_hides_on_a_till_that_hides_cost(self):
		with patch.object(item_details, "_till_hides_cost", return_value=True):
			result = item_details.get_full_pricing_and_batch_details("_Test Item")
		self.assertEqual(result["valuation_rate"], 0)
		self.assertTrue(all(p["cost"] == 0 for p in result["price_lists"]))

	def test_the_endpoint_sends_cost_where_the_till_shows_it(self):
		with (
			patch.object(item_details, "_till_hides_cost", return_value=False),
			patch.object(item_details, "_without_cost") as strip,
		):
			item_details.get_full_pricing_and_batch_details("_Test Item")
		strip.assert_not_called()

	def test_no_till_means_nothing_hidden(self):
		"""A desk user with no POS Profile sees valuation in ERPNext anyway."""
		with patch.object(item_details, "get_current_pos_profile_lite", side_effect=frappe.ValidationError("no till")):
			messages = len(frappe.local.message_log)
			self.assertFalse(item_details._till_hides_cost())
			self.assertEqual(len(frappe.local.message_log), messages)


class TestTakingsAreNotSent(ClosingCase):
	def _summary(self):
		from klik_pos.api import payment

		sales = [{"mode_of_payment": "Cash", "total_amount": 500.0, "transactions": 3}]
		frappe.set_user(OPENER)
		with (
			self._as(CASHIER_ROLES),
			patch.object(payment, "get_current_pos_opening_entry", return_value=self.entry),
			patch.object(payment, "_fetch_opening_sales_data", return_value=sales),
		):
			return payment.get_opening_entry_payment_summary()

	def test_hide_expected_amount_leaves_the_takings_out(self):
		frappe.db.set_value("POS Profile", self.till, {ALLOW_CLOSING: 1, "custom_hide_expected_amount": 1})
		summary = self._summary()
		self.assertTrue(summary["success"])
		self.assertTrue(summary["figures_hidden"])
		cash = next(m for m in summary["data"] if m["name"] == "Cash")
		self.assertEqual((cash["amount"], cash["transactions"]), (0.0, 0))

	def test_a_till_that_shows_them_is_unchanged(self):
		frappe.db.set_value("POS Profile", self.till, {ALLOW_CLOSING: 1, "custom_hide_expected_amount": 0})
		summary = self._summary()
		self.assertFalse(summary.get("figures_hidden"))
		self.assertEqual(next(m for m in summary["data"] if m["name"] == "Cash")["amount"], 500.0)
