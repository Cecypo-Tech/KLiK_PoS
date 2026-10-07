"""Quick entry: "item, qty, rate" lines typed into the POS, each item matched by its code.

An exact item code wins; otherwise the one item whose code contains the text, then the one
item whose name contains it. Several matches fail the line - guessing would put the wrong
item on a sale. Only items this till sells can match.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe
from erpnext.stock.doctype.item.test_item import make_item
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item.quick_entry import MAX_LINES, match_items, parse_line

GROUP = "_Test KLiK Quick Entry"
OTHER_GROUP = "_Test KLiK Quick Entry Other"


def _group(name):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}).insert()


class TestQuickEntryMatching(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		_group(GROUP)
		_group(OTHER_GROUP)
		if not frappe.db.exists("Item Attribute", "_Test QE Size"):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": "_Test QE Size",
					"item_attribute_values": [{"attribute_value": "Small", "abbr": "S"}],
				}
			).insert()
		for code, name, group, extra in (
			("QE-MIMOSA-01", "Mimosa Juice", GROUP, {}),
			("QE-TWIST300", "Twist 300ml", GROUP, {}),
			("QE-TWIST3000", "Twist 3 litre", GROUP, {}),
			("QE-MIMOSA-OFF", "Mimosa Off", GROUP, {"disabled": 1}),
			("QE-MIMOSA-ELSEWHERE", "Mimosa Elsewhere", OTHER_GROUP, {}),
			("QE-NOT-FOR-SALE", "Not For Sale", GROUP, {"is_sales_item": 0}),
			("QE-SHIRT", "Shirt Template", GROUP, {"has_variants": 1, "attributes": [{"attribute": "_Test QE Size"}]}),
		):
			if not frappe.db.exists("Item", code):
				make_item(code, {"item_name": name, "item_group": group, "is_stock_item": 0, **extra})
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.till = frappe._dict(
			name="_Test Quick Entry Till",
			company=cls.company,
			warehouse=frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 0}, "name"),
			selling_price_list=frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name"),
			item_groups=[frappe._dict(item_group=GROUP)],
			custom_enable_service_items=1,
		)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for code in frappe.get_all("Item", filters={"name": ["like", "QE-%"]}, pluck="name"):
			frappe.delete_doc("Item", code, force=True)
		frappe.delete_doc("Item Attribute", "_Test QE Size", force=True, ignore_missing=True)
		frappe.db.commit()
		super().tearDownClass()

	def _match(self, *queries, till=None):
		till = till or self.till
		with (
			patch("klik_pos.api.item.quick_entry.get_current_pos_profile", return_value=till),
			patch("klik_pos.api.item.item_listing.get_current_pos_profile", return_value=till),
		):
			return match_items(list(queries))

	def _one(self, query):
		return self._match(query)[0]

	def test_an_exact_code_wins_over_codes_that_contain_it(self):
		result = self._one("qe-twist300")
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["item"]["id"], "QE-TWIST300")

	def test_one_code_containing_the_text_is_used(self):
		result = self._one("mimosa")
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["item"]["id"], "QE-MIMOSA-01")

	def test_several_codes_containing_the_text_fail_the_line(self):
		result = self._one("twist30")
		self.assertEqual(result["status"], "many")
		self.assertEqual(sorted(result["candidates"]), ["QE-TWIST300", "QE-TWIST3000"])
		self.assertIsNone(result["item"])

	def test_the_name_is_tried_when_no_code_has_the_text(self):
		result = self._one("juice")
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["item"]["id"], "QE-MIMOSA-01")

	def test_nothing_matching_says_so(self):
		self.assertEqual(self._one("qe-nothing-like-this")["status"], "none")

	def test_disabled_unsold_and_other_group_items_never_match(self):
		for query in ("QE-MIMOSA-OFF", "QE-MIMOSA-ELSEWHERE", "QE-NOT-FOR-SALE"):
			self.assertEqual(self._one(query)["status"], "none", query)

	def test_like_wildcards_are_taken_literally(self):
		self.assertEqual(self._one("qe-%")["status"], "none")
		self.assertEqual(self._one("qe_twist300")["status"], "none")

	def test_the_matched_item_is_ready_for_the_cart(self):
		item = self._one("QE-TWIST300")["item"]
		for field in ("id", "name", "price", "uom"):
			self.assertIn(field, item)

	def test_answers_come_back_in_the_order_asked(self):
		results = self._match("juice", "twist30", "juice")
		self.assertEqual([r["query"] for r in results], ["juice", "twist30", "juice"])
		self.assertEqual([r["status"] for r in results], ["ok", "many", "ok"])

	def test_a_huge_paste_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._match(*["x"] * (MAX_LINES + 1))

	def test_an_item_with_variants_asks_for_the_variant(self):
		result = self._one("QE-SHIRT")
		self.assertEqual(result["status"], "template")
		self.assertEqual(result["candidates"], ["QE-SHIRT"])

	def test_an_item_the_till_does_not_offer_is_unavailable(self):
		"""A service item on a till without service items: matched, but not sellable here."""
		till = frappe._dict(self.till, custom_enable_service_items=0)
		result = self._match("QE-TWIST300", till=till)[0]
		self.assertEqual(result["status"], "unavailable")
		self.assertIsNone(result["item"])

	def test_a_backslash_is_taken_literally(self):
		self.assertEqual(self._one("qe\\twist")["status"], "none")

	def test_a_payload_that_is_not_a_list_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			match_items('{"a": 1}')

	def test_someone_who_cannot_read_items_matches_nothing(self):
		user = "quick-entry-no-item-read@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "NoItem", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.set_user(user)
		try:
			self.assertEqual(self._one("QE-TWIST300")["status"], "none")
		finally:
			frappe.set_user("Administrator")


class TestQuickEntryParsing(TestCase):
	def test_parse_line_table(self):
		cases = [
			# text, item_tokens, numbers, qty, qty_ambiguous, rate
			("5pcs AP004", ["AP004"], [], 5, False, None),
			("5 pcs AP004", ["AP004"], [], 5, False, None),
			("AP004 5pc", ["AP004"], [], 5, False, None),
			("ap004 5PCE", ["ap004"], [], 5, False, None),
			("AP004 x5", ["AP004"], [], 5, False, None),
			("AP004 x 5", ["AP004"], [], 5, False, None),
			("5x AP004", ["AP004"], [], 5, False, None),
			("qty 5 AP004", ["AP004"], [], 5, False, None),
			("AP004 qty:5", ["AP004"], [], 5, False, None),
			("AP004 2.5pcs", ["AP004"], [], 2.5, False, None),
			("AP377\tAP377\t2", ["AP377", "AP377"], ["2"], None, False, None),
			("51360-TMJ-T01-B ASIMCO    KY14094    4", ["51360-TMJ-T01-B", "ASIMCO", "KY14094"], ["4"], None, False, None),
			("AP004", ["AP004"], [], None, False, None),
			("AP004 @220", ["AP004"], [], None, False, 220),
			("AP004 @ 220 3", ["AP004"], ["3"], None, False, 220),
			("5pcs AP004 x2", ["AP004"], [], 2, True, None),
			("5pcs AP004 7", ["AP004"], ["7"], 5, False, None),
			("BOX 5", ["BOX"], ["5"], None, False, None),
			# legacy comma lines, read exactly as before
			("mimosa, 1", ["mimosa"], [], 1, False, None),
			("twist300, 5, 220", ["twist300"], [], 5, False, 220),
			("mimosa juice, 2", ["mimosa juice"], [], 2, False, None),
			("rope, .5", ["rope"], [], 0.5, False, None),
		]
		for text, tokens, numbers, qty, ambiguous, rate in cases:
			parsed = parse_line(text)
			self.assertEqual(
				(parsed["item_tokens"], parsed["numbers"], parsed["qty"], parsed["qty_ambiguous"], parsed["rate"], parsed["error"]),
				(tokens, numbers, qty, ambiguous, rate, None),
				text,
			)

	def test_unreadable_values_say_why(self):
		self.assertEqual(parse_line("mimosa, 0")["error"], "Quantity must be more than 0")
		self.assertEqual(parse_line("0pcs mimosa")["error"], "Quantity must be more than 0")
		self.assertEqual(parse_line("mimosa, 1, cheap")["error"], "Rate must be a number")
		self.assertEqual(parse_line("mimosa, 1, 0")["error"], "Rate must be more than 0 (leave it out for the till's price)")
		self.assertEqual(parse_line("mimosa @0")["error"], "Rate must be more than 0 (leave it out for the till's price)")

	def test_punctuation_alone_is_not_an_item(self):
		self.assertEqual(parse_line("AP004 - 2 *")["item_tokens"], ["AP004"])
