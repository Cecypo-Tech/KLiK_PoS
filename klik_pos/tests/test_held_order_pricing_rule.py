"""Holding an order must keep the till's price, whatever a Pricing Rule says.

A held order is a draft Sales Order. klik_pos built its lines with `rate` only and saved it
with pricing rules switched on, so ERPNext's calculate_item_rate took the
`has_pricing_rules` branch and replaced the cashier's rate with the rule's price. On
production a 5% margin rule turned a keyed 2,000 into 2,040 x 1.05 = 2,142. Recalling the
order then loaded 2,142 as the item's price and showed the customer a 142 discount they
were never given. The Sales Invoice path was protected in d7812f1; the held order was not.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import _get_active_pos_profile
from klik_pos.api.sales_order import create_held_order, get_held_order_details

ITEM_GROUP = "TEST-HELD-MARGIN-GROUP"
ITEM_CODE = "TEST-HELD-MARGIN-ITEM"
RULE_TITLE = "TEST-HELD-MARGIN-RULE"

LIST_RATE = 2040.0
MARGIN_PERCENT = 5.0
TILL_RATE = 2000.0


class TestHeldOrderPricingRule(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pos_profile = _get_active_pos_profile()
		cls.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": ITEM_GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = ITEM_CODE
			item.item_name = ITEM_CODE
			item.item_group = ITEM_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": ITEM_CODE,
				"price_list": cls.pos_profile.selling_price_list,
				"selling": 1,
				"price_list_rate": LIST_RATE,
			}
		).insert(ignore_permissions=True)

		# The production rule: a percentage margin, no discount.
		rule = frappe.new_doc("Pricing Rule")
		rule.title = RULE_TITLE
		rule.apply_on = "Item Code"
		rule.append("items", {"item_code": ITEM_CODE})
		rule.selling = 1
		rule.company = cls.pos_profile.company
		rule.currency = frappe.get_cached_value("Company", cls.pos_profile.company, "default_currency")
		rule.price_or_product_discount = "Price"
		rule.rate_or_discount = "Discount Percentage"
		rule.discount_percentage = 0
		rule.margin_type = "Percentage"
		rule.margin_rate_or_amount = MARGIN_PERCENT
		rule.insert(ignore_permissions=True)
		cls.pricing_rule = rule.name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for name in frappe.get_all(
			"Sales Order Item", filters={"item_code": ITEM_CODE}, pluck="parent", distinct=True
		):
			frappe.delete_doc("Sales Order", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Pricing Rule", cls.pricing_rule):
			frappe.delete_doc("Pricing Rule", cls.pricing_rule, force=True, ignore_permissions=True)
		for name in frappe.get_all("Item Price", filters={"item_code": ITEM_CODE}, pluck="name"):
			frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", ITEM_CODE):
			frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
		if frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _hold(self, price, original_price, held_order_id=None):
		"""The payload OrderSummary.holdCurrentOrder sends after the cashier keys TILL_RATE."""
		result = create_held_order(
			{
				"customer": {"id": self.customer},
				"items": [
					{
						"id": ITEM_CODE,
						"item_code": ITEM_CODE,
						"name": ITEM_CODE,
						"quantity": 1,
						"price": price,
						"original_price": original_price,
						"uom": "Nos",
					}
				],
				"itemDiscounts": {
					ITEM_CODE: {
						"customRate": TILL_RATE,
						"customRateIncludesTax": True,
						"discountAmount": 0,
						"discountPercentage": 0,
					}
				},
				"status": "held",
				"held_order_id": held_order_id,
			}
		)
		self.assertTrue(result["success"], msg=result.get("message"))
		return result["order_name"]

	def _row(self, order_name):
		return frappe.get_doc("Sales Order", order_name).items[0]

	def test_a_margin_rule_does_not_reprice_the_held_line(self):
		row = self._row(self._hold(TILL_RATE, LIST_RATE))

		self.assertEqual(flt(row.rate), TILL_RATE)
		self.assertEqual(flt(row.amount), TILL_RATE)

	def test_the_held_line_records_the_list_price_without_the_margin(self):
		row = self._row(self._hold(TILL_RATE, LIST_RATE))

		self.assertEqual(flt(row.price_list_rate), LIST_RATE)
		self.assertFalse(row.pricing_rules)

	def test_recalling_the_order_returns_the_till_price(self):
		details = get_held_order_details(self._hold(TILL_RATE, LIST_RATE))

		self.assertTrue(details["success"], msg=details.get("message"))
		self.assertEqual(flt(details["items"][0]["price"]), TILL_RATE)

	def test_holding_and_recalling_three_times_never_moves_the_price(self):
		"""The reported sequence: hold, recall, hold again - the discount grew each time."""
		order_name = self._hold(TILL_RATE, LIST_RATE)

		for _cycle in range(3):
			recalled = get_held_order_details(order_name)["items"][0]
			# heldOrderToCart puts the recalled price in both price and original_price.
			order_name = self._hold(TILL_RATE, recalled["price"], held_order_id=order_name)

		row = self._row(order_name)
		self.assertEqual(flt(row.rate), TILL_RATE)
		self.assertEqual(flt(row.price_list_rate), LIST_RATE)
