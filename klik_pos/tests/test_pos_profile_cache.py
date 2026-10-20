"""The till a shift resolves to is cached by shift name - and a rolled-back shift's name is
handed out again. Left cached, the next shift by that name resolved to a till that no longer
existed ("POS Profile _Test Opening Conflict b490b2 not found" in a full test run)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.klik_pos import utils


class TestACachedTillDoesNotOutliveItsShift(FrappeTestCase):
	def test_a_rolled_back_shift_leaves_nothing_cached(self):
		shift = "POS-OPE-ROLLED-BACK"
		with patch.object(sales_invoice, "get_current_pos_opening_entry", return_value=shift), patch.object(
			frappe.db, "get_value", return_value="_Test Till Gone"
		):
			self.assertEqual(utils._resolve_pos_profile_name(), "_Test Till Gone")
		key = f"{frappe.session.user}|{shift}"
		self.assertIn(key, utils._till_cache())
		frappe.db.rollback()
		self.assertNotIn(key, utils._till_cache())


class TestADeletedShiftLeavesNothingCached(FrappeTestCase):
	"""A deleted shift's name is handed out again too: the series steps back. A test cleanup
	that deleted its shift and till left "POS Profile TEST-RCPT-TILL not found" for the next
	module whose shift took the name."""

	def test_deleting_a_shift_forgets_its_till(self):
		from klik_pos.tests.test_held_order_orphans import _opening_entry

		shift = _opening_entry()
		key = f"{frappe.session.user}|{shift.name}"
		utils._till_cache()[key] = "_Test Till Gone"
		frappe.db.set_value("POS Opening Entry", shift.name, "docstatus", 2)
		frappe.delete_doc("POS Opening Entry", shift.name, force=True, ignore_permissions=True, ignore_on_trash=True)
		self.assertNotIn(key, utils._till_cache())


class TestACachedTillLastsOneRequest(FrappeTestCase):
	"""Each web worker kept its own process-wide cache, so a deletion handled by one worker
	left the others resolving the reused shift name to the deleted till."""

	def test_the_next_request_looks_the_till_up_again(self):
		shift = "POS-OPE-NEXT-REQUEST"
		with patch.object(sales_invoice, "get_current_pos_opening_entry", return_value=shift):
			with patch.object(frappe.db, "get_value", return_value="_Test Till Before"):
				self.assertEqual(utils._resolve_pos_profile_name(), "_Test Till Before")
			del frappe.local.klik_till_cache  # what a new request starts with
			with patch.object(frappe.db, "get_value", return_value="_Test Till Now"):
				self.assertEqual(utils._resolve_pos_profile_name(), "_Test Till Now")
