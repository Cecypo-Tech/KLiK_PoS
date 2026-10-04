"""The listing's WHERE, rebuilt without joins, must return exactly what it returned before.

Joining tabBin without a warehouse (or an item with several bundles) multiplied rows, which
forced DISTINCT, and DISTINCT made MariaDB build and sort the whole catalogue for every
page. The rewrite tests stock and bundles with EXISTS instead. The first class pins today's
results for every branch of the old query (it passes before the rewrite on purpose); the
rest pin what the rewrite adds: bundles found by their item code, a stable order between
equal names, and the indexes.

Stock is pinned high (5 on hand) so the Python hide-unavailable filter never drops a row:
what comes back is what the SQL chose.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_listing
from klik_pos.tests import listing_fixtures as fx


class ListingQueryCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fx.make_listing_fixtures()

	@classmethod
	def tearDownClass(cls):
		fx.drop_listing_fixtures()
		super().tearDownClass()

	def _codes(
		self,
		hide_unavailable,
		warehouse=fx.WAREHOUSE,
		include_service_items=0,
		stock=5,
		enhanced_search=0,
		**kwargs,
	):
		kwargs.setdefault("category", fx.GROUP)
		kwargs.setdefault("limit", 100)
		with (
			patch.object(
				item_listing,
				"_get_pos_context",
				return_value=fx.pos_context(
					hide_unavailable, warehouse, include_service_items, enhanced_search
				),
			),
			patch.object(
				item_listing,
				"_fetch_batch_stock",
				side_effect=lambda codes, wh: {code: stock for code in codes},
			),
		):
			result = item_listing.get_items(**kwargs)
		return result, [item["id"] for item in result["items"]]


class TestTheWhereKeepsItsMeaning(ListingQueryCase):
	STOCKABLE = frozenset(
		{fx.STOCKED, fx.EMPTY, fx.ELSEWHERE, fx.NEGATIVE, fx.TEMPLATE, fx.BUNDLE, *fx.TWINS}
	)

	def _assert(self, expected, **kwargs):
		result, codes = self._codes(**kwargs)
		self.assertEqual(set(codes), set(expected))
		self.assertEqual(len(codes), len(set(codes)), "an item was listed twice")
		self.assertEqual(result["total_count"], len(expected))

	def test_everything_sellable_without_services(self):
		self._assert(self.STOCKABLE, hide_unavailable=False)

	def test_services_included_when_the_till_sells_them(self):
		self._assert(self.STOCKABLE | {fx.SERVICE}, hide_unavailable=False, include_service_items=1)

	def test_hide_unavailable_with_services_in_the_till_warehouse(self):
		self._assert(
			{fx.STOCKED, fx.NEGATIVE, fx.SERVICE, fx.TEMPLATE, fx.BUNDLE},
			hide_unavailable=True,
			include_service_items=1,
		)

	def test_hide_unavailable_with_services_without_a_warehouse(self):
		self._assert(
			{fx.STOCKED, fx.ELSEWHERE, fx.NEGATIVE, fx.SERVICE, fx.TEMPLATE, fx.BUNDLE},
			hide_unavailable=True,
			include_service_items=1,
			warehouse=None,
		)

	def test_hide_unavailable_in_the_till_warehouse(self):
		# A negative-stock item still needs a Bin row in the till's warehouse on this branch -
		# a quirk of the old join, kept rather than changed inside a performance rewrite.
		self._assert({fx.STOCKED, fx.TEMPLATE, fx.BUNDLE}, hide_unavailable=True)

	def test_hide_unavailable_without_a_warehouse(self):
		self._assert(
			{fx.STOCKED, fx.ELSEWHERE, fx.NEGATIVE, fx.TEMPLATE, fx.BUNDLE},
			hide_unavailable=True,
			warehouse=None,
		)


class TestBundlesAreRecognised(ListingQueryCase):
	def test_a_bundle_named_by_its_series_is_still_a_bundle(self):
		result, _codes = self._codes(hide_unavailable=False)
		bundle = next(item for item in result["items"] if item["id"] == fx.BUNDLE)
		self.assertTrue(bundle["is_product_bundle"])
		self.assertEqual(
			frappe.db.get_value("Product Bundle", {"new_item_code": fx.BUNDLE}, "name"), fx.BUNDLE_DOC_NAME
		)


class TestEqualNamesPageCleanly(ListingQueryCase):
	def test_paging_one_at_a_time_through_equal_names_repeats_and_skips_nothing(self):
		seen = []
		for offset in range(len(fx.TWINS)):
			_result, codes = self._codes(hide_unavailable=False, item_codes=fx.TWINS, limit=1, offset=offset)
			seen.extend(codes)
		self.assertEqual(seen, sorted(fx.TWINS))


class TestListingIndexes(FrappeTestCase):
	def test_the_patch_adds_both_indexes(self):
		from klik_pos.patches.v16_0 import add_item_listing_indexes

		add_item_listing_indexes.execute()
		# Two columns, in this order: Frappe's schema sync drops a single-column index on a field
		# the DocType does not mark search_index, and leaves a composite alone.
		bundle_index = frappe.db.sql(
			"SHOW INDEX FROM `tabProduct Bundle` WHERE Key_name = %s",
			("klik_pos_bundle_item_disabled",),
			as_dict=True,
		)
		self.assertEqual(
			[row.Column_name for row in sorted(bundle_index, key=lambda row: row.Seq_in_index)],
			["new_item_code", "disabled"],
		)
		self.assertTrue(frappe.db.has_index("tabItem", "klik_pos_item_group_name"))
