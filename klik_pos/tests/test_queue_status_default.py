"""queue_status says where an invoice is in the background queue - and nothing for one never sent there.

The field shipped with default "Queued", so every Sales Invoice started out "Queued" and only
the worker ever changed it: invoices submitted directly read "Queued" for good, the dashboard
counted every draft as a queued sale (13 on Dev Co), and any draft could be "retried" into
the worker.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import retry_failed_sales_invoice, submit_draft_invoice
from klik_pos.tests.test_held_order_orphans import COMPANY, CUSTOMER, ITEM


def _draft(**values):
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = CUSTOMER
	invoice.company = COMPANY
	invoice.append("items", {"item_code": ITEM, "qty": 1, "rate": 10})
	invoice.insert(ignore_permissions=True)
	if values:
		frappe.db.set_value("Sales Invoice", invoice.name, values, update_modified=False)
	return invoice


def _queue_status(invoice):
	return frappe.db.get_value("Sales Invoice", invoice.name, "queue_status") or ""


class TestQueueStatusStartsBlank(FrappeTestCase):
	def test_the_shipped_field_has_no_default_and_is_not_copied(self):
		path = frappe.get_app_path("klik_pos", "klik_pos", "custom", "sales_invoice.json")
		with open(path) as f:
			field = next(d for d in json.load(f)["custom_fields"] if d["fieldname"] == "queue_status")
		self.assertFalse(field["default"])
		# An amendment or a return is a new invoice; it has not been queued either.
		self.assertEqual(field["no_copy"], 1)

	def test_a_new_invoice_is_not_queued(self):
		self.assertEqual(_queue_status(_draft()), "")

	def test_an_invoice_submitted_directly_is_not_queued(self):
		draft = _draft()
		frappe.set_user("Administrator")
		self.assertTrue(submit_draft_invoice(draft.name)["success"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft.name, "docstatus"), 1)
		self.assertEqual(_queue_status(draft), "")

	def test_reserving_stock_does_not_mark_a_direct_submit_as_queued(self):
		# before_submit releases a reserving invoice's stock; that alone is no queue history.
		from unittest.mock import patch

		from klik_pos.api import sales_invoice

		draft = _draft()
		frappe.set_user("Administrator")
		with patch.object(sales_invoice, "_should_reserve_stock", return_value=True):
			self.assertTrue(submit_draft_invoice(draft.name)["success"])
		self.assertEqual(_queue_status(draft), "")

	def test_a_queued_sale_submitted_any_way_reads_submitted(self):
		from unittest.mock import patch

		from klik_pos.api import sales_invoice

		draft = _draft(queue_status="Queued", enable_background_invoice_submission=0)
		frappe.set_user("Administrator")
		with patch.object(sales_invoice, "_should_reserve_stock", return_value=True):
			self.assertTrue(submit_draft_invoice(draft.name)["success"])
		self.assertEqual(_queue_status(draft), "Submitted")

	def test_a_draft_never_sent_to_the_queue_cannot_be_retried_into_it(self):
		result = retry_failed_sales_invoice(_draft().name)
		self.assertFalse(result.get("success"))


class TestPatchClearsTheDefault(FrappeTestCase):
	def _run_patch(self):
		from klik_pos.patches.v16_0.clear_default_queue_status import execute

		execute()

	def test_never_queued_invoices_are_cleared(self):
		draft = _draft(queue_status="Queued", enable_background_invoice_submission=0)
		submitted = _draft(queue_status="Queued", enable_background_invoice_submission=0, docstatus=1)

		self._run_patch()

		self.assertEqual(_queue_status(draft), "")
		self.assertEqual(_queue_status(submitted), "")

	def test_a_sale_waiting_for_the_worker_stays_queued(self):
		waiting = _draft(queue_status="Queued", enable_background_invoice_submission=1)
		self._run_patch()
		self.assertEqual(_queue_status(waiting), "Queued")

	def test_a_queued_sale_already_submitted_reads_submitted(self):
		done = _draft(queue_status="Queued", enable_background_invoice_submission=1, docstatus=1)
		self._run_patch()
		self.assertEqual(_queue_status(done), "Submitted")

	def test_failed_and_processing_are_left_alone(self):
		failed = _draft(queue_status="Failed", enable_background_invoice_submission=0)
		processing = _draft(queue_status="Processing", enable_background_invoice_submission=1)
		self._run_patch()
		self.assertEqual(_queue_status(failed), "Failed")
		self.assertEqual(_queue_status(processing), "Processing")
