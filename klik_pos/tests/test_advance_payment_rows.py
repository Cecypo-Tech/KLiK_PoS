"""Which Payment Entries settled this invoice, read once and shared.

The invoice list and the detail page both derived 'how was this paid' from the payments
table alone. With M-Pesa arriving as advances that table shows the mode with no money;
the money is on Sales Invoice Advance rows pointing at Payment Entries. One reader serves
both surfaces so they cannot disagree.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.mpesa import _allocate_receipts_before_submit
from klik_pos.api.payment_rows import advance_payment_rows, merge_payment_rows, mode_label
from klik_pos.api.sales_invoice import get_sales_invoices
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


class TestModeLabel(FrappeTestCase):
	"""The 'Cash/Mpesa' label every list shows. A Payment Entry made outside the POS
	(a customer advance, a bank reconciliation) may have no Mode of Payment - ERPNext does
	not require one - and the label used to crash on it, taking the whole tab down."""

	def test_a_blank_mode_does_not_take_the_label_down(self):
		rows = [{"mode_of_payment": "Cash", "amount": 50.0}, {"mode_of_payment": None, "amount": 450.0}]
		self.assertEqual(mode_label(rows), "Cash")

	def test_known_modes_are_joined_once_each(self):
		rows = [
			{"mode_of_payment": "Cash", "amount": 50.0},
			{"mode_of_payment": "Mpesa", "amount": 100.0},
			{"mode_of_payment": "Mpesa", "amount": 200.0},
		]
		self.assertEqual(mode_label(rows), "Cash/Mpesa")

	def test_no_known_mode_reads_as_a_dash(self):
		self.assertEqual(mode_label([]), "-")
		self.assertEqual(mode_label([{"mode_of_payment": None, "amount": 10.0}]), "-")


class TestAdvancePaymentRows(MpesaFirstCase):
	def test_a_payment_entry_without_a_mode_is_labelled_by_its_account(self):
		"""Mode of Payment is optional on a Payment Entry. On a site whose money arrives as
		plain customer advances it is blank on every one, so the row names the account
		the money went to instead - what the accountant chose, and still filterable."""
		invoice = self._submitted(rate=100, receipts=[self._receipt(100, "254700000403")])
		entry = advance_payment_rows([invoice.name])[invoice.name][0]["payment_entry"]
		frappe.db.set_value("Payment Entry", entry, "mode_of_payment", None, update_modified=False)

		rows = advance_payment_rows([invoice.name])[invoice.name]

		self.assertEqual(rows[0]["mode_of_payment"], frappe.db.get_value("Payment Entry", entry, "paid_to"))

	def test_invoice_history_survives_a_payment_entry_without_a_mode(self):
		"""Regression: one such invoice in a page returned
		'sequence item 1: expected str instance, NoneType found' and Invoice History
		showed 'Error loading invoices' for every sale."""
		invoice = self._draft(rate=200, posting_date=frappe.utils.nowdate())
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": 100})
		invoice.save(ignore_permissions=True)
		invoice = self._record(invoice, self._receipt(100, "254700000404"))
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		entry = advance_payment_rows([invoice.name])[invoice.name][0]["payment_entry"]
		frappe.db.set_value("Payment Entry", entry, "mode_of_payment", None, update_modified=False)
		frappe.db.set_value(
			"Sales Invoice", invoice.name, "custom_pos_opening_entry", "POS-OPE-TEST-BLANK-MODE", update_modified=False
		)

		result = get_sales_invoices(search=invoice.name, skip_opening_entry_filter=True, surface="history")

		self.assertTrue(result["success"], result.get("error"))
		row = next(r for r in result["data"] if r["name"] == invoice.name)
		account = frappe.db.get_value("Payment Entry", entry, "paid_to")
		self.assertEqual(row["mode_of_payment"], f"Cash/{account}")

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

	def test_a_site_without_the_phone_column_still_gets_its_rows(self):
		"""The phone number is a custom field of frappe_mpsa_payments' own patch.

		Selecting it unguarded turns every invoice list and detail page into a 500 on a
		site that has not got the column - the whole surface, not just the phone.
		"""
		invoice = self._submitted(rate=100, receipts=[self._receipt(100, "254700000401")])
		real_has_column = frappe.local.db.has_column

		def without_the_phone_column(doctype, column):
			if doctype == "Payment Entry" and column == "custom_mpesa_phone_number":
				return False
			return real_has_column(doctype, column)

		with patch.object(frappe.local.db, "has_column", side_effect=without_the_phone_column):
			rows = advance_payment_rows([invoice.name])[invoice.name]

		self.assertEqual([r["amount"] for r in rows], [100.0])
		self.assertIsNone(rows[0]["phone_number"], "the row survives without the column")
		self.assertTrue(rows[0]["reference_no"], "the receipt number still comes through")

	def test_a_cancelled_invoice_is_not_still_reported_as_settled(self):
		"""ERPNext leaves the advance rows on a cancelled invoice (it only deletes them
		when a single payment is unlinked), so the reader has to exclude it itself - or
		Invoice History shows a cancelled sale as paid by M-Pesa."""
		invoice = self._submitted(rate=100, receipts=[self._receipt(100, "254700000402")])
		self.assertIn(invoice.name, advance_payment_rows([invoice.name]))

		invoice.cancel()

		self.assertEqual(advance_payment_rows([invoice.name]), {})

	def _submitted(self, rate, receipts):
		invoice = self._record(self._draft(rate=rate), *receipts)
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		return invoice
