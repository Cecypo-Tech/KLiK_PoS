"""Item details at the till must not need Batch read for an item that has no batches.

A till role (e.g. ERPNext Express's sales role) reads Item, Item Price and Bin but not
Batch; the lookup 403'd on every plain item and the till lost its pricing details.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_details
from klik_pos.tests.test_price_list_recording import ITEM, _ensure_fixtures


def _no_batch_read(original):
	def get_list(doctype, *args, **kwargs):
		if doctype == "Batch":
			raise frappe.PermissionError("Insufficient Permission for Batch")
		return original(doctype, *args, **kwargs)

	return get_list


class TestItemDetailsBatchRead(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_fixtures()

	def test_plain_item_details_without_batch_read(self):
		self.assertFalse(frappe.db.get_value("Item", ITEM, "has_batch_no"))
		with patch.object(item_details.frappe, "get_list", _no_batch_read(frappe.get_list)):
			result = item_details.get_full_pricing_and_batch_details(ITEM)
		self.assertEqual(result.get("batches") or [], [])
