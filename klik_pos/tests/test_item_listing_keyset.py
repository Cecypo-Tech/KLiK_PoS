"""Paging by "continue after the last item" instead of "skip N rows".

OFFSET makes page N read and discard every row before it; a cursor (the last row's name
and code) lets MariaDB start right there on the item_name index. The count is the most
expensive query on a page and the till only needs it once per browse, so later pages may
skip it. has_more comes from reading one row past the page.
"""

from unittest.mock import patch

from klik_pos.tests import listing_fixtures as fx
from klik_pos.tests.test_item_listing_query import ListingQueryCase


class TestKeysetPaging(ListingQueryCase):
	def _walk(self, limit, hide_unavailable=False, stock=5, item_codes=None):
		cursor, seen, requests = None, [], 0
		while True:
			params = {"limit": limit, "item_codes": item_codes or fx.EVERY}
			if cursor:
				params.update(**cursor, include_count=0)
			result, codes = self._codes(hide_unavailable, include_service_items=1, stock=stock, **params)
			requests += 1
			seen.extend(codes)
			if not result["has_more"]:
				self.assertIsNone(result["next_cursor"])
				return seen, requests
			self.assertIsNotNone(result["next_cursor"], "has_more without a cursor would stall the till")
			self.assertNotEqual(result["next_cursor"], cursor, "the cursor did not move")
			cursor = result["next_cursor"]
			self.assertLess(requests, 50, "paging did not terminate")

	def test_walking_by_cursor_returns_every_item_once_in_name_order(self):
		_result, one_page = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=100)
		seen, _requests = self._walk(limit=2)
		self.assertEqual(seen, one_page)
		self.assertEqual(sorted(seen), sorted(fx.EVERY))

	def test_a_page_the_hide_filter_empties_still_moves_the_cursor(self):
		# Nothing on hand: the stocked item's page comes back empty, and paging must step
		# over it to the template behind it - not stop there, and not ask for it forever.
		seen, requests = self._walk(
			limit=1, hide_unavailable=True, stock=0, item_codes=[fx.STOCKED, fx.TEMPLATE]
		)
		self.assertEqual(seen, [fx.TEMPLATE])
		self.assertEqual(requests, 2)

	def test_later_pages_can_skip_the_count(self):
		first, _codes = self._codes(False, item_codes=fx.EVERY, limit=2)
		self.assertIsInstance(first["total_count"], int)
		later, _codes = self._codes(
			False,
			item_codes=fx.EVERY,
			limit=2,
			**first["next_cursor"],
			include_count=0,
		)
		self.assertIsNone(later["total_count"])

	def test_has_more_is_exact_at_the_boundary(self):
		everything = len(fx.EVERY)
		full, _codes = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=everything)
		self.assertFalse(full["has_more"])
		self.assertIsNone(full["next_cursor"])
		short, _codes = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=everything - 1)
		self.assertTrue(short["has_more"])

	def test_offset_paging_still_works_for_older_tills(self):
		by_cursor, _requests = self._walk(limit=3)
		by_offset, offset = [], 0
		while True:
			result, codes = self._codes(
				False, include_service_items=1, item_codes=fx.EVERY, limit=3, offset=offset
			)
			by_offset.extend(codes)
			self.assertIsInstance(result["total_count"], int)
			if not result["has_more"]:
				break
			offset = result["next_offset"]
		self.assertEqual(by_offset, by_cursor)


class TestCursorPagesStayPermissionScoped(ListingQueryCase):
	def test_a_cursor_page_still_applies_the_permission_condition(self):
		# apply_sql_permissions adds its condition right after the query's first WHERE, so the
		# keyset clause has to share that WHERE. A continuation that lost the condition would list
		# items the reader may not see.
		first, _codes = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=2)
		after = {**first["next_cursor"], "include_count": 0}
		_result, rest = self._codes(False, include_service_items=1, item_codes=fx.EVERY, **after)
		self.assertGreater(len(rest), 2)
		barred = [rest[0], rest[-1]]

		def restrict(doctype, *args, **kwargs):
			if doctype != "Item":
				return ""
			return "`tabItem`.`name` NOT IN ({})".format(", ".join(f"'{code}'" for code in barred))

		with patch("klik_pos.api.sql_builder.build_match_conditions", side_effect=restrict):
			_result, permitted = self._codes(False, include_service_items=1, item_codes=fx.EVERY, **after)

		self.assertEqual(permitted, [code for code in rest if code not in barred])


class TestGroupOrder(TestKeysetPaging):
	"""Browsing lists items group by group - the list view heads each group - and the cursor
	carries the group, so paging across a group boundary neither repeats nor skips an item."""

	OTHER_GROUP = "TEST-LISTQ-AAA"  # sorts before fx.GROUP
	MOVED = [fx.TWINS[1], fx.STOCKED]

	def setUp(self):
		super().setUp()
		import frappe

		if not frappe.db.exists("Item Group", self.OTHER_GROUP):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": self.OTHER_GROUP, "parent_item_group": "All Item Groups"}
			).insert(ignore_permissions=True)
		for code in self.MOVED:
			frappe.db.set_value("Item", code, "item_group", self.OTHER_GROUP, update_modified=False)
		self.addCleanup(
			lambda: [frappe.db.set_value("Item", code, "item_group", fx.GROUP, update_modified=False) for code in self.MOVED]
		)

	def _codes(self, *args, **kwargs):
		kwargs.setdefault("category", "all")
		return super()._codes(*args, **kwargs)

	def test_items_come_group_by_group(self):
		import frappe

		_result, listed = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=100)
		in_db_order = frappe.get_all(
			"Item", filters={"name": ["in", fx.EVERY]}, order_by="item_group asc, item_name asc, name asc", pluck="name"
		)
		self.assertEqual(listed, in_db_order)
		self.assertEqual(set(listed[:2]), set(self.MOVED))

	def test_the_next_page_marker_carries_the_group(self):
		first, _codes = self._codes(False, include_service_items=1, item_codes=fx.EVERY, limit=1)
		self.assertEqual(first["next_cursor"]["after_group"], self.OTHER_GROUP)

	def test_a_search_keeps_its_best_match_order(self):
		_result, listed = self._codes(False, include_service_items=1, item_codes=fx.EVERY, search="LISTQ", limit=100)
		self.assertNotEqual(set(listed[:2]), set(self.MOVED))
