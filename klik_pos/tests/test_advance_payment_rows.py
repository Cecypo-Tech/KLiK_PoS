"""Which Payment Entries settled this invoice, read once and shared.

The invoice list and the detail page both derived 'how was this paid' from the payments
table alone. With M-Pesa arriving as advances that table shows the mode with no money;
the money is on Sales Invoice Advance rows pointing at Payment Entries. One reader serves
both surfaces so they cannot disagree.
"""

from frappe.tests.utils import FrappeTestCase

from klik_pos.api.mpesa import _allocate_receipts_before_submit
from klik_pos.api.payment_rows import advance_payment_rows, merge_payment_rows
from klik_pos.tests.test_mpesa_payment_entry_first import MpesaFirstCase


class TestMergePaymentRows(FrappeTestCase):
	def test_an_advance_replaces_the_zero_row_of_its_mode(self):
		merged = merge_payment_rows(
			[{"mode_of_payment": "Mpesa", "amount": 0.0}, {"mode_of_payment": "Cash", "amount": 50.0}],
			[{"mode_of_payment": "Mpesa", "amount": 450.0, "reference_no": "TX1", "phone_number": "2547", "payment_entry": "PE-1"}],
		)
		self.assertEqual([(r["mode_of_payment"], r["amount"]) for r in merged], [("Cash", 50.0), ("Mpesa", 450.0)])

	def test_a_real_payment_row_is_never_dropped(self):
		merged = merge_payment_rows(
			[{"mode_of_payment": "Mpesa", "amount": 100.0}],
			[{"mode_of_payment": "Mpesa", "amount": 450.0, "reference_no": "TX1", "phone_number": None, "payment_entry": "PE-1"}],
		)
		self.assertEqual(len(merged), 2)

	def test_no_advances_means_the_rows_come_back_untouched(self):
		rows = [{"mode_of_payment": "Cash", "amount": 50.0}]
		self.assertEqual(merge_payment_rows(rows, []), rows)


class TestAdvancePaymentRows(MpesaFirstCase):
	def test_reads_mode_amount_and_receipt_details_from_the_payment_entry(self):
		invoice = self._record(self._draft(rate=500), self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()

		rows = advance_payment_rows([invoice.name])[invoice.name]

		self.assertEqual([r["amount"] for r in rows], [250.0, 250.0])
		self.assertEqual([r["phone_number"] for r in rows], ["254700000201", "254700000202"])
		self.assertTrue(all(r["reference_no"] for r in rows))
		self.assertTrue(all(r["payment_entry"] for r in rows))

	def test_an_invoice_with_no_advances_is_absent_not_empty_list(self):
		self.assertEqual(advance_payment_rows(["SINV-DOES-NOT-EXIST"]), {})
