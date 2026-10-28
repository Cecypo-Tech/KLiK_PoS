"""An item that is not serial- or batch-tracked has no serials or batches to look up.

The till asks whenever it does not know an item's tracking, and the lookup reads Serial No /
Batch with the cashier's permissions: on a site with no tracked items at all, a cashier without
read on Serial No logged "Get Serial Nos Error for <item>" on every cart line."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from klik_pos.api.item import item_details


def _item(**tracking):
	return frappe.db.get_value("Item", {"disabled": 0, **tracking}, "name")


class TestUntrackedItemLookups(IntegrationTestCase):
	def setUp(self):
		till = frappe._dict(warehouse="Stores - X")
		self.till = patch.object(item_details, "get_current_pos_profile", return_value=till)
		self.till.start()
		self.addCleanup(self.till.stop)

	def _refused(self):
		return patch.object(item_details.frappe, "get_list", side_effect=frappe.PermissionError)

	def test_no_serials_for_an_item_without_them_and_no_lookup(self):
		item = _item(has_serial_no=0)
		with self._refused() as get_list:
			self.assertEqual(item_details.get_serial_nos_for_item(item), [])
		get_list.assert_not_called()

	def test_no_batches_for_an_item_without_them_and_no_lookup(self):
		item = _item(has_batch_no=0)
		with self._refused() as get_list:
			self.assertEqual(item_details.get_batch_nos_with_qty(item), [])
		get_list.assert_not_called()

	def test_a_serial_tracked_item_is_still_looked_up(self):
		with (
			patch.object(item_details.frappe.db, "get_value", return_value=1),
			patch.object(item_details.frappe, "get_list", return_value=[]) as get_list,
		):
			item_details.get_serial_nos_for_item("Any Serial Item")
		get_list.assert_called_once()

	def test_a_batch_tracked_item_is_still_looked_up(self):
		with (
			patch.object(item_details.frappe.db, "get_value", return_value=1),
			patch.object(item_details.frappe, "get_list", return_value=[]) as get_list,
		):
			item_details.get_batch_nos_with_qty("Any Batch Item")
		get_list.assert_called_once()
