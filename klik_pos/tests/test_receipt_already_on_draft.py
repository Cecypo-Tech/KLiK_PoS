"""A draft that already carries a receipt takes the same pick again at submit.

A submit that fails after the insert leaves its draft with the receipt recorded on it.
Reopened at the till, that receipt is still pickable, and picking it was refused as
"already on this invoice" - CS-07449 on FAC.Allparts, ten times, while each Hold in between
left another held copy of the sale.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.mpesa import attach_mpesa_receipts


class TestReceiptAlreadyOnDraft(FrappeTestCase):
	def test_a_receipt_already_on_the_draft_is_not_refused(self):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = "_Test Customer"
		invoice.append(
			"custom_mpesa_reconciled_payments",
			{"mpesa_c2b_payment_register": "MPC2B-TEST-1", "transid": "TESTTRANS1", "amount": 100, "mode_of_payment": "Mpesa"},
		)

		attach_mpesa_receipts(invoice, {"mode_of_payment": "Mpesa", "payments": ["MPC2B-TEST-1"]})

		self.assertEqual(
			[c.mpesa_c2b_payment_register for c in invoice.custom_mpesa_reconciled_payments], ["MPC2B-TEST-1"]
		)
		# ERPNext refuses a POS invoice with no payment row for its mode.
		self.assertEqual([p.mode_of_payment for p in invoice.payments], ["Mpesa"])
