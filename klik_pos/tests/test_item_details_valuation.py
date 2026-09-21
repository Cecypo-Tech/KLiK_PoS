"""The item details endpoint must report the ledger's CURRENT valuation, not a running sum.

It used to divide the sum of every Stock Ledger Entry's stock_value_difference by the balance
quantity. That sum drifts from the real stock value once a Stock Reconciliation is in the
history: an item the ledger (and Bin) valued at 400 was reported to the POS tooltip as 440.46,
while the cart line - reading the per-warehouse rate from the same response - said 400.
"""

from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item.item_details import _current_valuation_rate


class TestCurrentValuationRate(FrappeTestCase):
	def test_single_warehouse_reports_the_ledgers_current_rate(self):
		# The drifted running sum (40081.8) must not leak into the answer.
		warehouse_map = {"Stores - DC": {"bal_qty": 91.0, "bal_val": 40081.8, "val_rate": 400.0}}

		self.assertEqual(_current_valuation_rate(warehouse_map, fallback=50.0), 400.0)

	def test_several_warehouses_are_weighted_by_the_stock_they_hold(self):
		warehouse_map = {
			"A": {"bal_qty": 10.0, "bal_val": 0.0, "val_rate": 100.0},
			"B": {"bal_qty": 30.0, "bal_val": 0.0, "val_rate": 200.0},
		}

		self.assertEqual(_current_valuation_rate(warehouse_map, fallback=0.0), 175.0)

	def test_warehouses_with_no_stock_do_not_dilute_the_rate(self):
		warehouse_map = {
			"A": {"bal_qty": 0.0, "bal_val": 0.0, "val_rate": 999.0},
			"B": {"bal_qty": 5.0, "bal_val": 0.0, "val_rate": 80.0},
		}

		self.assertEqual(_current_valuation_rate(warehouse_map, fallback=0.0), 80.0)

	def test_no_stock_anywhere_falls_back_to_the_last_known_rate(self):
		self.assertEqual(_current_valuation_rate({}, fallback=42.0), 42.0)
		self.assertEqual(
			_current_valuation_rate({"A": {"bal_qty": -2.0, "bal_val": 0.0, "val_rate": 10.0}}, fallback=42.0),
			42.0,
		)
