"""Item groups for the till: their own small request, and only when asked for.

The category bar waited for the whole first page of items (~230 KB on dev) because the
groups came inside it, and every later page, category click and search paid to compute
them again. get_item_groups returns just the groups; get_items computes them only when
include_groups is set (on by default, for tills that predate the flag).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_listing


class TestItemGroupLoading(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_the_listing_skips_groups_when_not_asked(self):
		self.assertEqual(item_listing.get_items(limit=5, offset=0, include_groups=0)["item_groups"], [])

	def test_the_listing_still_sends_groups_by_default(self):
		self.assertTrue(item_listing.get_items(limit=5, offset=0)["item_groups"])

	def test_the_groups_request_matches_what_the_listing_sends(self):
		self.assertEqual(
			item_listing.get_item_groups(),
			item_listing.get_items(limit=5, offset=0)["item_groups"],
		)

	def test_the_unused_guest_endpoint_is_gone(self):
		# get_item_groups_for_pos was guest-accessible and ran one COUNT per group.
		with self.assertRaises(ImportError):
			from klik_pos.api.item import item_groups
