"""Finishing a draft must not tell the cashier its payment methods were refreshed.

ERPNext raises "Payment methods refreshed. Please review before proceeding." whenever it
refills the till's modes over payment rows already on the invoice. A draft has them, so every
draft finished at the till showed it - in the till's error style - though the rows are wiped
and written from the cashier's own payments straight after.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import create_draft_invoice, submit_draft_invoice

PAYLOAD = {
	"customer": {"id": "Walk In"},
	"items": [{"id": "Consulting", "item_code": "Consulting", "quantity": 1, "price": 10, "uom": "Nos"}],
	"paymentMethods": [],
	"amountPaid": 0,
	"businessType": "B2C",
}


class TestDraftSubmitRaisesNoRefreshToast(FrappeTestCase):
	def test_no_refresh_toast_when_a_draft_with_payment_rows_is_finished(self):
		frappe.set_user("Administrator")
		draft = create_draft_invoice({**PAYLOAD, "status": "held"})
		name = draft.get("invoice_name") or (draft.get("invoice") or {}).get("name")
		if not name:
			self.skipTest(f"no draft could be made on this site: {draft}")
		if not frappe.db.count("Sales Invoice Payment", {"parent": name}):
			self.skipTest("the draft has no payment rows: nothing for ERPNext to refresh")

		mode = frappe.db.get_value("Sales Invoice Payment", {"parent": name}, "mode_of_payment")
		total = frappe.db.get_value("Sales Invoice", name, "grand_total")
		paid = {**PAYLOAD, "paymentMethods": [{"method": mode, "amount": total}], "amountPaid": total}

		# Whether the submit then goes through (this site may have no open shift) is beside
		# the point: the refill runs before that.
		with patch("frappe.toast") as toast:
			submit_draft_invoice(name, paid)

		refreshed = [c for c in toast.call_args_list if "refreshed" in str(c)]
		self.assertEqual(refreshed, [])
