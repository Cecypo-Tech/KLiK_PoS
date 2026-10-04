"""What a listing page carries over the wire.

`tax_info` was 29% of a 250-item page (66 of 230 KB on dev) and every item carried an
identical copy. A till that asks (compact_tax=1) gets each distinct tax profile once and a
key per item; a till that doesn't - one opened before the deploy - gets the old shape.
`preparationTime` was a constant nothing read.
"""

from klik_pos.tests.test_item_listing_query import ListingQueryCase


class TestListingPayload(ListingQueryCase):
	def test_compact_pages_send_each_tax_profile_once(self):
		result, codes = self._codes(False, compact_tax=1)
		self.assertTrue(codes)
		profiles = result["tax_profiles"]
		for item in result["items"]:
			self.assertNotIn("tax_info", item)
			self.assertIn(item["tax_key"], profiles)
		# The fixture items share their tax treatment: one profile for the whole page.
		self.assertLess(len(profiles), len(result["items"]))

	def test_a_profile_is_exactly_the_tax_info_it_replaces(self):
		compact, _codes = self._codes(False, compact_tax=1)
		inline, _codes = self._codes(False)
		inline_by_id = {item["id"]: item["tax_info"] for item in inline["items"]}
		for item in compact["items"]:
			self.assertEqual(compact["tax_profiles"][item["tax_key"]], inline_by_id[item["id"]])

	def test_tax_details_stay_inline_unless_asked(self):
		result, _codes = self._codes(False)
		self.assertNotIn("tax_profiles", result)
		self.assertTrue(all("tax_info" in item for item in result["items"]))

	def test_the_dead_preparation_time_is_gone(self):
		result, _codes = self._codes(False)
		self.assertTrue(all("preparationTime" not in item for item in result["items"]))
