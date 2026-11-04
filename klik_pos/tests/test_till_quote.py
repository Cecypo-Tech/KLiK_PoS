"""Quote mode: the till saves a Quotation, which is never limited by stock."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import quotation
from klik_pos.setup.quote_fields import ensure_quote_fields
from klik_pos.tests.test_held_order_visibility import CUSTOMER, ITEM
from klik_pos.tests.test_opening_conflict import _profile, _shift


def _payload(item, qty, rate, los_qty=0):
	return {
		"customer": {"id": CUSTOMER},
		"items": [{"id": item, "item_code": item, "quantity": qty, "los_qty": los_qty, "price": rate, "uom": "Nos"}],
		"status": "held",
	}


class TestCreateQuote(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_quote_fields()
		self.addCleanup(frappe.db.rollback)
		_shift(_profile(), "Administrator")

	def test_quote_takes_more_than_stock_and_prices_all_of_it(self):
		res = quotation.create_quote(_payload(ITEM, qty=15, rate=100))
		self.assertTrue(res["success"], res)
		q = frappe.get_doc("Quotation", res["quote_name"])
		self.assertEqual(q.docstatus, 1)
		self.assertEqual(q.status, "Open")
		self.assertEqual(q.items[0].qty, 15)
		# Dev Co taxes are inclusive of the rate, so the quote totals what the cart priced.
		self.assertEqual(q.grand_total, 1500)
		self.assertTrue(q.custom_klik_cart_meta)
		self.assertTrue(q.custom_pos_profile)

	def test_los_qty_in_payload_is_folded_back(self):
		res = quotation.create_quote(_payload(ITEM, qty=10, los_qty=5, rate=100))
		self.assertTrue(res["success"], res)
		self.assertEqual(frappe.db.get_value("Quotation Item", {"parent": res["quote_name"]}, "qty"), 15)

	def test_breach_is_refused_and_nothing_is_saved(self):
		before = frappe.db.count("Quotation")
		with patch(
			"cecypo_powerpack.min_selling_price.validate_min_selling_price",
			side_effect=frappe.ValidationError("Price approval needed"),
		):
			res = quotation.create_quote(_payload(ITEM, qty=1, rate=1))
		self.assertFalse(res["success"])
		self.assertIn("Price approval needed", res["message"])
		self.assertEqual(frappe.db.count("Quotation"), before)
