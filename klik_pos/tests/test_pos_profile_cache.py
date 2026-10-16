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
		self.assertIn(key, utils._cached_pos_profiles)
		frappe.db.rollback()
		self.assertNotIn(key, utils._cached_pos_profiles)
