import unittest

import frappe

from klik_pos.klik_pos.utils import error_reason


class TestErrorReason(unittest.TestCase):
	def test_a_lock_timeout_reads_as_busy_not_as_a_database_error(self):
		raw = frappe.QueryTimeoutError(1205, "Lock wait timeout exceeded; try restarting transaction")
		self.assertNotIn("1205", error_reason(raw))
		self.assertIn("busy", error_reason(raw))
		self.assertIn("busy", error_reason(frappe.QueryDeadlockError(1213, "Deadlock found")))

	def test_a_worded_error_keeps_its_words(self):
		self.assertEqual(error_reason(frappe.ValidationError("Qty cannot be a fraction")), "Qty cannot be a fraction")
