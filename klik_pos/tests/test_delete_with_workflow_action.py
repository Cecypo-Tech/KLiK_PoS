"""A draft a Sales Order/Invoice workflow is waiting on can still be deleted.

An active workflow puts an open Workflow Action on every draft. Frappe's own delete clears
them in on_trash, but klik's link checks ran first and refused: discarding an M-Pesa order,
deleting a held order and the shift-close sweep all failed on such a site.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.mpesa_order import delete_order
from klik_pos.api.sales_invoice import _check_discardable_links
from klik_pos.tests.test_held_order_mpesa_checkout import _draft
from klik_pos.tests.test_held_order_orphans import _held_order


def _workflow_action(doc):
	frappe.get_doc(
		{
			"doctype": "Workflow Action",
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"status": "Open",
			"workflow_state": "Draft",
		}
	).insert(ignore_permissions=True)


class TestDeleteWithWorkflowAction(FrappeTestCase):
	def test_a_held_order_with_a_workflow_action_is_deleted(self):
		so = _held_order()
		_workflow_action(so)
		delete_order(so)
		self.assertFalse(frappe.db.exists("Sales Order", so.name))
		self.assertFalse(frappe.db.exists("Workflow Action", {"reference_name": so.name}))

	def test_a_draft_invoice_with_a_workflow_action_may_be_discarded(self):
		draft = _draft()
		_workflow_action(draft)
		_check_discardable_links(draft)  # raises LinkExistsError when it refuses
