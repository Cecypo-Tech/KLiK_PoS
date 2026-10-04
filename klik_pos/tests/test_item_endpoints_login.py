"""The till's item endpoints answer logged-in users only; nothing outside the till calls them."""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import (
	item_details,
	item_price,
	item_search,
	item_stock,
	item_tax_details,
	pricing,
	pricing_rules,
)

METHODS = [
	item_details.get_serial_nos_for_item,
	item_price.get_item_price_for_customer,
	item_search.get_item_by_barcode,
	item_search.get_item_by_identifier,
	item_stock.get_stock_updates,
	item_stock.get_item_stock,
	item_tax_details.get_item_tax_details,
	pricing.get_cart_pricing,
	pricing_rules.apply_pricing_rules_to_cart,
]


class TestItemEndpointsNeedLogin(FrappeTestCase):
	def test_guests_are_refused_and_users_are_not(self):
		for method in METHODS:
			frappe.is_whitelisted(method)
		frappe.set_user("Guest")
		try:
			for method in METHODS:
				with self.subTest(method=method.__name__), self.assertRaises(frappe.PermissionError):
					frappe.is_whitelisted(method)
		finally:
			frappe.set_user("Administrator")
