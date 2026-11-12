"""POS Profile 'Cost Display': Hidden / Valuation / Last Purchase Cost.

The last purchase cost is the newest submitted, non-return Purchase Invoice line of the till's
company, per stock UOM and excluding tax.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_details, item_listing
from klik_pos.api.item.cost import cost_mode, last_purchase_rates
from klik_pos.tests.test_item_listing_cost_price import (
	BOX_FACTOR,
	BOX_ITEM_CODE,
	ITEM_CODES,
	TestGetItemsCostPrice,
)

ITEM = ITEM_CODES[0]


def _purchase(name, company, item_code, rate, date, factor=1, docstatus=1, is_return=0):
	"""A bare Purchase Invoice row and line: only what last_purchase_rates reads."""
	frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"name": name,
			"company": company,
			"posting_date": date,
			"posting_time": "10:00:00",
			"docstatus": docstatus,
			"is_return": is_return,
		}
	).db_insert()
	frappe.get_doc(
		{
			"doctype": "Purchase Invoice Item",
			"name": f"{name}-1",
			"parent": name,
			"parenttype": "Purchase Invoice",
			"parentfield": "items",
			"idx": 1,
			"item_code": item_code,
			"base_net_rate": rate,
			"conversion_factor": factor,
		}
	).db_insert()


def _forget_purchases():
	names = frappe.get_all("Purchase Invoice", {"name": ["like", "TEST-LPC-%"]}, pluck="name")
	if names:
		frappe.db.delete("Purchase Invoice Item", {"parent": ["in", names]})
		frappe.db.delete("Purchase Invoice", {"name": ["in", names]})


class TestCostMode(FrappeTestCase):
	def test_the_two_shown_modes_pass_through(self):
		self.assertEqual(cost_mode({"custom_cost_display": "Valuation"}), "Valuation")
		self.assertEqual(cost_mode({"custom_cost_display": "Last Purchase Cost"}), "Last Purchase Cost")

	def test_anything_else_is_hidden(self):
		for profile in ({"custom_cost_display": "Hidden"}, {"custom_cost_display": None}, {}, None):
			self.assertEqual(cost_mode(profile), "Hidden")


class TestLastPurchaseRates(TestGetItemsCostPrice):
	def setUp(self):
		_forget_purchases()
		self.addCleanup(_forget_purchases)

	def test_the_newest_submitted_purchase_wins(self):
		_purchase("TEST-LPC-1", self.company, ITEM, 50, "2026-01-01")
		_purchase("TEST-LPC-2", self.company, ITEM, 60, "2026-03-01")
		_purchase("TEST-LPC-3", self.company, ITEM, 99, "2026-04-01", docstatus=0)
		_purchase("TEST-LPC-4", self.company, ITEM, 99, "2026-05-01", is_return=1)
		_purchase("TEST-LPC-5", "_Not This Company", ITEM, 99, "2026-06-01")

		rate, date = last_purchase_rates([ITEM], self.company)[ITEM]

		self.assertEqual(rate, 60)
		self.assertEqual(str(date), "2026-03-01")

	def test_a_purchase_by_the_box_is_costed_per_stock_uom(self):
		_purchase("TEST-LPC-6", self.company, ITEM, 120, "2026-03-01", factor=12)

		self.assertEqual(last_purchase_rates([ITEM], self.company)[ITEM][0], 10)

	def test_an_item_never_bought_is_absent(self):
		self.assertEqual(last_purchase_rates([ITEM], self.company), {})

	def test_the_list_quotes_last_purchase_cost_in_the_listed_uom(self):
		_purchase("TEST-LPC-7", self.company, BOX_ITEM_CODE, 10, "2026-03-01")

		item = self._items(mode="Last Purchase Cost")[BOX_ITEM_CODE]

		self.assertEqual(item["last_purchase_cost"], 10 * BOX_FACTOR)
		self.assertEqual(str(item["last_purchase_date"]), "2026-03-01")

	def test_a_hidden_till_gets_no_purchase_cost(self):
		_purchase("TEST-LPC-8", self.company, ITEM, 10, "2026-03-01")

		with patch.object(item_listing, "last_purchase_rates") as rates:
			item = self._items(mode="Hidden")[ITEM]

		rates.assert_not_called()
		self.assertEqual(item["last_purchase_cost"], 0)

	def test_details_work_price_list_margin_from_last_purchase_cost(self):
		_purchase("TEST-LPC-9", self.company, ITEM, 7, "2026-03-01")
		details = {"price_lists": [{"rate": 10.0, "cost": 3.0, "margin": 7.0, "margin_pct": 233.3}]}

		with patch.object(item_details, "_till_cost_mode", return_value=("Last Purchase Cost", self.company)):
			result = item_details._with_cost_display(ITEM, details)

		self.assertEqual(result["last_purchase_rate"], 7)
		self.assertEqual(result["price_lists"][0]["cost"], 7)
		self.assertEqual(result["price_lists"][0]["margin"], 3)


class TestHideCostPricePatch(FrappeTestCase):
	def test_ticked_tills_stay_hidden_and_the_rest_see_valuation(self):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		from klik_pos.patches.v16_0 import hide_cost_price_to_cost_display as p

		create_custom_field("POS Profile", {"fieldname": p.OLD, "label": "Hide Cost Price", "fieldtype": "Check"})
		profiles = frappe.get_all("POS Profile", pluck="name", limit=2)
		if len(profiles) < 2:
			self.skipTest("needs two POS Profiles")
		frappe.db.set_value("POS Profile", profiles[0], p.OLD, 1, update_modified=False)
		frappe.db.set_value("POS Profile", profiles[1], p.OLD, 0, update_modified=False)

		p.execute()
		p.execute()  # a second run finds nothing to do

		self.assertEqual(frappe.db.get_value("POS Profile", profiles[0], p.NEW), "Hidden")
		self.assertEqual(frappe.db.get_value("POS Profile", profiles[1], p.NEW), "Valuation")
		self.assertFalse(frappe.db.exists("Custom Field", {"dt": "POS Profile", "fieldname": p.OLD}))
