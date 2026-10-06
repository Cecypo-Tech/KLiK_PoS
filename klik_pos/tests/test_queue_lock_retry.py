"""A queued sale that loses a database lock race is retried, not failed.

On a busy counter two workers post sales at once and MySQL kills one with a deadlock. The
worker caught it and marked the sale failed (Allparts: 4 of 196 queued sales on one day), when
the same submit a second later goes through.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.tests.test_queue_status_default import _draft


def _deadlock():
	return frappe.QueryDeadlockError((1213, "Deadlock found when trying to get lock"))


class TestQueueLockRetry(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.draft = _draft(queue_status="Queued")
		# The worker rolls back between attempts; in a test that would also roll away the draft.
		self.rollback = patch.object(frappe.db, "rollback").start()
		self.sleep = patch.object(sales_invoice.time, "sleep").start()
		self.notify = patch.object(sales_invoice, "_notify_queue_failure").start()
		self.addCleanup(patch.stopall)

	def _run(self, *outcomes):
		with patch.object(sales_invoice, "_submit_queued_invoice", side_effect=list(outcomes)) as submit:
			result = sales_invoice.process_queued_sales_invoice(self.draft.name)
		return result, submit

	def test_a_deadlock_is_retried_and_the_sale_posts(self):
		result, submit = self._run(_deadlock(), {"success": True})
		self.assertTrue(result["success"])
		self.assertEqual(submit.call_count, 2)
		self.notify.assert_not_called()
		self.assertNotEqual(frappe.db.get_value("Sales Invoice", self.draft.name, "queue_status"), "Failed")

	def test_a_lock_wait_timeout_is_retried(self):
		timeout = frappe.QueryTimeoutError((1205, "Lock wait timeout exceeded"))
		result, submit = self._run(timeout, {"success": True})
		self.assertTrue(result["success"])
		self.assertEqual(submit.call_count, 2)

	def test_three_deadlocks_fail_the_sale_and_alert_once(self):
		result, submit = self._run(_deadlock(), _deadlock(), _deadlock())
		self.assertFalse(result["success"])
		self.assertEqual(submit.call_count, sales_invoice.QUEUE_LOCK_ATTEMPTS)
		self.notify.assert_called_once()
		self.assertEqual(frappe.db.get_value("Sales Invoice", self.draft.name, "queue_status"), "Failed")

	def test_any_other_error_fails_at_once(self):
		result, submit = self._run(frappe.ValidationError("Not enough stock"))
		self.assertFalse(result["success"])
		self.assertEqual(submit.call_count, 1)
		self.sleep.assert_not_called()
		self.notify.assert_called_once()


class TestQueuedSubmitSkipsTheProcessingSave(FrappeTestCase):
	def test_the_tax_rows_are_written_once_by_the_submit(self):
		# The Processing marker was a full save - validate plus a rewrite of the item-wise tax
		# rows, where every deadlock happened - inside a transaction nobody else can read anyway.
		frappe.set_user("Administrator")
		draft = _draft(queue_status="Queued")
		from erpnext.controllers.accounts_controller import AccountsController

		with patch.object(AccountsController, "on_update", autospec=True) as on_update:
			result = sales_invoice.process_queued_sales_invoice(draft.name)
		self.assertTrue(result["success"], result.get("message"))
		# Submit itself runs on_update once; the Processing save made it twice.
		self.assertEqual(on_update.call_count, 1)
		row = frappe.db.get_value(
			"Sales Invoice", draft.name, ["docstatus", "queue_status", "queue_attempts"], as_dict=True
		)
		self.assertEqual((row.docstatus, row.queue_status, row.queue_attempts), (1, "Submitted", 1))
