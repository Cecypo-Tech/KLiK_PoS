"""A draft the POS is finishing may have been submitted or cancelled elsewhere meanwhile.

submit_draft_invoice refused with prose only, so the payment dialog could not tell this
from any other failure and kept retrying the same invoice: every sale after it failed with
"Only Draft invoices can be submitted" (POS-01190, cancelled from the desk). The refusal now
says so in a form the dialog can act on.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import submit_draft_invoice


class TestSubmittingANonDraft(FrappeTestCase):
	def _refusal_for(self, docstatus):
		name = frappe.db.get_value("Sales Invoice", {"docstatus": docstatus}, "name")
		if not name:
			self.skipTest(f"no Sales Invoice with docstatus {docstatus} on this site")
		frappe.set_user("Administrator")
		return name, submit_draft_invoice(name)

	def test_a_cancelled_invoice_is_refused_with_a_code(self):
		name, result = self._refusal_for(2)
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "not_draft")
		self.assertEqual(result["docstatus"], 2)
		self.assertEqual(result["invoice_id"], name)

	def test_a_submitted_invoice_is_refused_with_a_code(self):
		_, result = self._refusal_for(1)
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "not_draft")
		self.assertEqual(result["docstatus"], 1)
