"""Quote mode: the till saves a Quotation, which is never limited by stock."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, add_months, cint, nowdate
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
		days = cint(frappe.db.get_single_value("CRM Settings", "default_valid_till"))
		expected = add_days(nowdate(), days) if days else add_months(nowdate(), 1)
		self.assertEqual(str(q.valid_till), str(expected))

	def test_los_qty_in_payload_is_folded_back(self):
		res = quotation.create_quote(_payload(ITEM, qty=10, los_qty=5, rate=100))
		self.assertTrue(res["success"], res)
		self.assertEqual(frappe.db.get_value("Quotation Item", {"parent": res["quote_name"]}, "qty"), 15)
		self.assertEqual(frappe.db.get_value("Quotation", res["quote_name"], "grand_total"), 1500)

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


class TestListAndLoadQuotes(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_quote_fields()
		self.addCleanup(frappe.db.rollback)
		_shift(_profile(), "Administrator")

	def _quote(self, qty=2, rate=100):
		res = quotation.create_quote(_payload(ITEM, qty=qty, rate=rate))
		self.assertTrue(res["success"], res)
		return res["quote_name"]

	def test_listed_for_any_till_of_the_company(self):
		name = self._quote()
		till_b = frappe.get_doc("POS Profile", _profile())
		with patch.object(quotation, "_get_active_pos_profile", return_value=till_b):
			res = quotation.get_quotes(limit=500)
		self.assertTrue(res["success"], res)
		row = next((r for r in res["data"] if r["name"] == name), None)
		self.assertIsNotNone(row)
		self.assertFalse(row["expired"])
		self.assertEqual(row["grand_total"], 200)

	def test_invoiced_quote_is_not_listed_and_wont_load(self):
		name = self._quote()
		si = frappe.new_doc("Sales Invoice")
		si.customer = CUSTOMER
		si.company = frappe.db.get_value("Quotation", name, "company")
		si.append("items", {"item_code": ITEM, "qty": 1, "rate": 1})
		si.custom_klik_quotation = name
		si.insert(ignore_permissions=True, ignore_mandatory=True)
		self.assertNotIn(name, [r["name"] for r in quotation.get_quotes(limit=500)["data"]])
		res = quotation.get_quote_details(name)
		self.assertFalse(res["success"])
		self.assertIn("already been invoiced", res["message"])

	def test_details_keep_quoted_price_until_valid_till(self):
		name = self._quote(qty=3, rate=100)
		res = quotation.get_quote_details(name)
		self.assertTrue(res["success"], res)
		self.assertFalse(res["expired"])
		item = res["items"][0]
		self.assertEqual(item["price"], 100)
		self.assertEqual(item["quantity"], 3)
		self.assertEqual(item["los_qty"], 0)
		self.assertEqual(res["customer"], CUSTOMER)

	def test_expired_quote_loads_without_its_prices(self):
		name = self._quote(rate=100)
		q = frappe.get_doc("Quotation", name)
		row = q.items[0]
		frappe.get_doc({
			"doctype": "Item Price", "item_code": ITEM, "uom": row.uom,
			"price_list": q.selling_price_list, "price_list_rate": 137,
		}).insert(ignore_permissions=True)
		q.db_set("valid_till", add_days(nowdate(), -1))
		res = quotation.get_quote_details(name)
		self.assertTrue(res["success"], res)
		self.assertTrue(res["expired"])
		item = res["items"][0]
		self.assertEqual(item["price"], 137)
		self.assertIsNone(item["customRate"])
		self.assertEqual(item["discountAmount"], 0)
		self.assertEqual(item["discountPercentage"], 0)

	def test_expired_quote_ignores_a_future_dated_price(self):
		name = self._quote(rate=100)
		q = frappe.get_doc("Quotation", name)
		uom = q.items[0].uom
		for rate, valid_from in ((137, None), (999, add_days(nowdate(), 1))):
			frappe.get_doc({
				"doctype": "Item Price", "item_code": ITEM, "uom": uom, "price_list": q.selling_price_list,
				"price_list_rate": rate, "valid_from": valid_from,
			}).insert(ignore_permissions=True)
		q.db_set("valid_till", add_days(nowdate(), -1))
		self.assertEqual(quotation.get_quote_details(name)["items"][0]["price"], 137)

	def test_expired_quote_scales_the_stock_uom_price_by_conversion(self):
		name = self._quote(rate=100)
		q = frappe.get_doc("Quotation", name)
		stock_uom = frappe.db.get_value("Item", ITEM, "stock_uom")
		box = frappe.get_doc({"doctype": "UOM", "uom_name": "_Test Quote Box"}).insert(ignore_permissions=True)
		item = frappe.get_doc("Item", ITEM)
		item.append("uoms", {"uom": box.name, "conversion_factor": 12})
		item.flags.ignore_validate = True
		item.save(ignore_permissions=True)
		frappe.db.set_value("Quotation Item", q.items[0].name, "uom", box.name)
		frappe.db.delete("Item Price", {"item_code": ITEM, "price_list": q.selling_price_list})
		frappe.get_doc({
			"doctype": "Item Price", "item_code": ITEM, "uom": stock_uom,
			"price_list": q.selling_price_list, "price_list_rate": 10,
		}).insert(ignore_permissions=True)
		q.db_set("valid_till", add_days(nowdate(), -1))
		self.assertEqual(quotation.get_quote_details(name)["items"][0]["price"], 120)
