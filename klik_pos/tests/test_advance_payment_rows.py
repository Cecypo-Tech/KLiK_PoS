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
from klik_pos.api.sales_invoice import get_customer_invoices_for_return, get_invoice_details, get_sales_invoices
from klik_pos.tests.test_mpesa_payment_entry_first import CUSTOMER, MpesaFirstCase


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

	def test_a_mode_less_advance_keeps_every_payments_table_row(self):
		"""An advance with no mode settles nothing in particular, so it cannot stand in for
		the Mpesa placeholder; the placeholder stays and the money is added."""
		merged = merge_payment_rows(
			[{"mode_of_payment": "Mpesa", "amount": 0.0}],
			[{"mode_of_payment": None, "paid_to": "Bank - TC", "amount": 450.0, "reference_no": None, "phone_number": None, "payment_entry": "PE-2"}],
		)
		self.assertEqual([(r["mode_of_payment"], r["amount"]) for r in merged], [("Mpesa", 0.0), (None, 450.0)])

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

	def test_a_mode_less_row_is_labelled_by_its_account(self):
		rows = [{"mode_of_payment": "Cash", "amount": 50.0}, {"mode_of_payment": None, "paid_to": "Bank - TC", "amount": 450.0}]
		self.assertEqual(mode_label(rows), "Cash/Bank - TC")

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
	def test_a_payment_entry_without_a_mode_keeps_a_blank_mode_and_carries_its_account(self):
		"""Mode of Payment is optional on a Payment Entry, and one made outside the POS (a
		customer advance an accountant recorded) usually has none. The row is shown, labelled
		by the account the money went to, but no mode is guessed for it: a mode is what the
		Closing Shift counts, and money the till never handled is not the cashier's to count."""
		invoice = self._submitted(rate=100, receipts=[self._receipt(100, "254700000403")])
		entry = self._mode_less_entry(invoice)

		rows = advance_payment_rows([invoice.name])[invoice.name]

		self.assertIsNone(rows[0]["mode_of_payment"])
		self.assertEqual(rows[0]["paid_to"], frappe.db.get_value("Payment Entry", entry, "paid_to"))
		self.assertEqual(mode_label(rows), rows[0]["paid_to"])

	def test_rows_say_which_shift_the_entry_was_stamped_with(self):
		"""The closing screens count an advance only when its entry was stamped with the
		shift being closed; money from outside the POS carries no shift."""
		invoice = self._submitted(rate=100, receipts=[self._receipt(100, "254700000405")])
		entry = advance_payment_rows([invoice.name])[invoice.name][0]["payment_entry"]
		self.assertIsNone(advance_payment_rows([invoice.name])[invoice.name][0]["pos_opening_entry"])

		frappe.db.set_value("Payment Entry", entry, "custom_pos_opening_entry", "POS-OPE-STAMP", update_modified=False)

		self.assertEqual(advance_payment_rows([invoice.name])[invoice.name][0]["pos_opening_entry"], "POS-OPE-STAMP")

	def _mode_less_entry(self, invoice, paid_to=None):
		"""Turn the invoice's first advance into one an accountant might have made."""
		entry = advance_payment_rows([invoice.name])[invoice.name][0]["payment_entry"]
		values = {"mode_of_payment": None}
		if paid_to:
			values["paid_to"] = paid_to
		frappe.db.set_value("Payment Entry", entry, values, update_modified=False)
		return entry

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
		entry = self._mode_less_entry(invoice)
		frappe.db.set_value(
			"Sales Invoice", invoice.name, "custom_pos_opening_entry", "POS-OPE-TEST-BLANK-MODE", update_modified=False
		)

		result = get_sales_invoices(search=invoice.name, skip_opening_entry_filter=True, surface="history")

		self.assertTrue(result["success"], result.get("error"))
		row = next(r for r in result["data"] if r["name"] == invoice.name)
		account = frappe.db.get_value("Payment Entry", entry, "paid_to")
		self.assertEqual(row["mode_of_payment"], f"Cash/{account}")
		self.assertEqual(
			{p["mode_of_payment"] for p in row["payment_methods"]},
			{"Cash", None},
			"only real Modes of Payment reach the rows the Closing Shift counts",
		)

		detail = get_invoice_details(invoice.name)
		self.assertTrue(detail["success"], detail.get("error"))
		self.assertEqual(detail["data"]["mode_of_payment"], f"Cash/{account}")

		picker = get_customer_invoices_for_return(CUSTOMER)
		self.assertTrue(picker["success"], picker.get("error"))
		picked = next(r for r in picker["data"] if r["name"] == invoice.name)
		self.assertEqual(picked["payment_method"], f"Cash/{account}")

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
