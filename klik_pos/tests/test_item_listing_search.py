"""What a typed search matches, and in what order.

The default search scanned code, name, description and barcode with %term% three times per
request (page, count, group counts). Description - the longest column - now belongs to
the enhanced search only; the default ranks an exact code or barcode match first so a
cashier typing a part number sees that part on top.
"""

import frappe

from klik_pos.api.item.search_utils import build_item_search_conditions
from klik_pos.tests import listing_fixtures as fx
from klik_pos.tests.test_item_listing_query import ListingQueryCase

PAD = "LISTQ-PAD"
PAD_REAR = "LISTQ-PAD-REAR"
DESC_ONLY = "LISTQ-DESC"
DESC_WORD = "zzlistqdescword"


class TestSearchShape(ListingQueryCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for code, name, description in (
			(PAD, "Brake pad front", ""),
			(PAD_REAR, "A brake pad rear", ""),
			(DESC_ONLY, "Plain thing", f"fits everything {DESC_WORD}"),
		):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": name,
						"description": description or name,
						"item_group": fx.GROUP,
						"stock_uom": "Nos",
						"is_stock_item": 1,
					}
				).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for code in (PAD, PAD_REAR, DESC_ONLY):
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def test_the_default_search_leaves_descriptions_to_the_enhanced_one(self):
		clauses, params = build_item_search_conditions("pad", False)
		self.assertNotIn("description", " ".join(clauses))
		self.assertEqual(params, ["%pad%", "%pad%", "%pad%"])
		enhanced, _params = build_item_search_conditions("pad", True)
		self.assertIn("description", " ".join(enhanced))

	def test_an_exact_code_comes_first(self):
		_result, codes = self._codes(False, search=PAD)
		self.assertEqual(codes[0], PAD)
		self.assertIn(PAD_REAR, codes)

	def test_a_description_word_needs_the_enhanced_search(self):
		_result, plain = self._codes(False, search=DESC_WORD)
		self.assertNotIn(DESC_ONLY, plain)
		_result, enhanced = self._codes(False, search=DESC_WORD, enhanced_search=1)
		self.assertIn(DESC_ONLY, enhanced)
