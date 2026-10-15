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

		self.enqueue = patch.object(sales_invoice.frappe, "enqueue").start()

	def _run(self, *outcomes, requeues=0):
		# A worker starts with a clean transaction; this one holds the uncommitted draft.
		with (
			patch.object(frappe.db, "transaction_writes", 0),
			patch.object(sales_invoice, "_submit_queued_invoice", side_effect=list(outcomes)) as submit,
		):
			result = sales_invoice.process_queued_sales_invoice(self.draft.name, requeues=requeues)
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

	def test_a_sale_that_keeps_losing_goes_back_on_the_queue(self):
		# CS-02402: three attempts inside two seconds all met the same minutes-long pile-up of
		# submits. Back of the queue, after a pause, instead of Failed.
		result, submit = self._run(*[_deadlock()] * sales_invoice.LOCK_RACE_ATTEMPTS)
		self.assertFalse(result["success"])
		self.assertEqual(submit.call_count, sales_invoice.LOCK_RACE_ATTEMPTS)
		self.enqueue.assert_called_once()
		args, kwargs = self.enqueue.call_args
		self.assertEqual(args[0], "klik_pos.api.sales_invoice.process_queued_sales_invoice")
		self.assertEqual((kwargs["invoice_name"], kwargs["requeues"]), (self.draft.name, 1))
		self.notify.assert_not_called()
		self.assertEqual(frappe.db.get_value("Sales Invoice", self.draft.name, "queue_status"), "Queued")

	def test_the_last_requeue_losing_fails_the_sale_and_alerts_once(self):
		result, submit = self._run(
			*[_deadlock()] * sales_invoice.LOCK_RACE_ATTEMPTS, requeues=sales_invoice.LOCK_RACE_REQUEUES
		)
		self.assertFalse(result["success"])
		self.enqueue.assert_not_called()
		self.notify.assert_called_once()
		self.assertEqual(frappe.db.get_value("Sales Invoice", self.draft.name, "queue_status"), "Failed")

	def test_a_requeue_that_cannot_be_queued_fails_the_sale(self):
		self.enqueue.side_effect = ConnectionError("redis down")
		result, submit = self._run(*[_deadlock()] * sales_invoice.LOCK_RACE_ATTEMPTS)
		self.assertFalse(result["success"])
		self.notify.assert_called_once()
		self.assertEqual(frappe.db.get_value("Sales Invoice", self.draft.name, "queue_status"), "Failed")

	def test_any_other_error_fails_at_once(self):
		result, submit = self._run(frappe.ValidationError("Not enough stock"))
		self.assertFalse(result["success"])
		self.assertEqual(submit.call_count, 1)
		self.sleep.assert_not_called()
		self.enqueue.assert_not_called()
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


class TestNoRetryAfterTheCallerWrote(FrappeTestCase):
	def test_a_race_after_earlier_writes_is_not_retried(self):
		# The rollback would take the caller's own writes with it, so it runs once and fails as before.
		frappe.set_user("Administrator")
		_draft()
		self.assertTrue(frappe.db.transaction_writes)
		calls = []

		def races():
			calls.append(1)
			raise _deadlock()

		with self.assertRaises(frappe.QueryDeadlockError):
			sales_invoice._retry_lock_race(races)
		self.assertEqual(len(calls), 1)

	def test_a_nested_call_leaves_the_retry_to_the_outer_one(self):
		frappe.set_user("Administrator")
		inner_calls = []

		def inner():
			inner_calls.append(1)
			raise _deadlock()

		def outer():
			return sales_invoice._retry_lock_race(inner)

		with (
			patch.object(frappe.db, "transaction_writes", 0),
			patch.object(frappe.db, "rollback"),
			patch.object(sales_invoice.time, "sleep"),
			self.assertRaises(frappe.QueryDeadlockError),
		):
			sales_invoice._retry_lock_race(outer)
		# Three outer attempts, one inner run each - not three times three.
		self.assertEqual(len(inner_calls), sales_invoice.LOCK_RACE_ATTEMPTS)
		self.assertIsNone(frappe.flags.klik_lock_race_retry)
