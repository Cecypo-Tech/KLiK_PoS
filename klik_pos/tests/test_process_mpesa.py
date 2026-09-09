import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.mpesa import process_mpesa
from klik_pos.api.sales_invoice import get_sales_invoices, submit_draft_invoice


class TestProcessMpesa(FrappeTestCase):
	"""Regression coverage for M-Pesa reconciliation in klik_pos's POS checkout.

	`process_mpesa` backs the "Add Selected Payments" button in the POS
	checkout's "M-Pesa Payment Options" modal. It used to append mpesa
	amounts directly into the draft Sales Invoice's own `payments` child
	table and submit the `Mpesa C2B Payment Register` row without setting
	`submit_payment`, which meant no `Payment Entry` was ever created -- the
	M-Pesa receipt was invisible to Payment Reconciliation, unallocated
	advances, and bank-reconciliation tooling, and any overpayment was
	stranded inside the one invoice's ledger with no way to reuse it on a
	future purchase.

	It now only records which register rows were selected
	(`custom_mpesa_reconciled_payments`, deferred/unconsumed). Finalization is
	Payment-Entry-first, in three phases: `process_mpesa` records the
	selected register rows as trace child rows on the draft;
	`_allocate_receipts_before_submit` mints one submitted Payment Entry per
	receipt (idempotently -- a retry reuses an entry a register row or trace
	row already names), appends one `Sales Invoice Advance` row per entry in
	selection order up to the invoice's payable total, plus a zero-amount
	`Sales Invoice Payment` row per mode (ERPNext demands at least one, and
	the invoice list, detail page and receipt all read the mode from that
	table), then saves the draft; after submit, `_finalize_mpesa_reconciliation`
	calls `invoice.update_against_document_in_jv()` (ERPNext skips this for
	POS invoices) to reconcile the advances, then consumes the register rows
	under the `is_manual_reconciliation` guard with `payment_entry` and
	`sales_invoice` set, and returns one row per receipt whose entry still
	holds unallocated money. There is no separate embedding step and no
	separate excess-credit Payment Entry: the invariant is one receipt, one
	Payment Entry, one bank line, and any overpaid remainder simply stays
	unallocated on that same entry -- the customer's credit, on the voucher
	that brought the money in. Both allocation phases run inline for
	`auto_submit=1`, or from `submit_draft_invoice` for the normal POS
	checkout path where submission happens in a later request.

	Fixtures are real documents (not mocks) so `invoice.save()`/`.submit()`,
	the register row's own `before_submit`/`on_submit`, and Payment
	Reconciliation are exercised end to end.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = "_Test Company"
		cls.customer = "_Test Customer"
		cls.other_customer = "_Test Customer 1"
		cls.shortcode = f"TSC{frappe.generate_hash(length=6).upper()}"
		cls.gateway_name = f"Test Mpesa Gateway {frappe.generate_hash(length=6)}"

		# Mpesa Settings.on_update() hard-commits real Payment Gateway/Account/
		# Mode of Payment records via an explicit frappe.db.commit() that this
		# test's rollback can't undo. db_insert() bypasses validate/on_update
		# entirely (raw INSERT), so the fixture stays transaction-safe.
		settings = frappe.get_doc(
			{
				"doctype": "Mpesa Settings",
				"payment_gateway_name": cls.gateway_name,
				"company": cls.company,
				"business_shortcode": cls.shortcode,
			}
		)
		settings.db_insert()

	def _draft_invoice(self, customer=None, rate=100):
		# is_pos=1 matches the real POS checkout draft this endpoint targets.
		# Posting date is pinned to a Fiscal Year that isn't restricted to a
		# specific company (unlike this site's "2026" Fiscal Year, which is
		# scoped only to "Dev Co"/"Temp Co" and would reject "_Test Company"
		# for today's date), so `.submit()` passes regardless of which
		# companies the site's real Fiscal Year records are scoped to.
		invoice = create_sales_invoice(
			company=self.company,
			customer=customer or self.customer,
			is_pos=1,
			rate=rate,
			posting_date="2029-06-15",
			do_not_save=True,
		)
		invoice.set_posting_time = 1
		invoice.posting_time = "10:00:00"
		return invoice

	def _make_c2b_payment(self, amount=100, msisdn="254700000001"):
		from klik_pos.tests.mpesa_fixtures import make_c2b_payment

		return make_c2b_payment(
			company=self.company, shortcode=self.shortcode, amount=amount, msisdn=msisdn
		)

	def test_records_traceability_without_touching_payments(self):
		invoice = self._draft_invoice()
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100, msisdn="254711111111")

		result = process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=row.name,
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=0,
		)

		self.assertTrue(result["success"])
		self.assertEqual(result["total_amount"], 100)
		self.assertFalse(result["submitted"])
		self.assertNotIn("mpesa_reconciliation", result)
		self.assertEqual(len(result["payments_added"]), 1)
		self.assertEqual(result["payments_added"][0]["reference"], row.transid)

		invoice.reload()
		self.assertEqual(invoice.docstatus, 0)
		# process_mpesa no longer touches the invoice's own payments table.
		self.assertEqual(len(invoice.payments), 0)

		self.assertEqual(len(invoice.custom_mpesa_reconciled_payments), 1)
		child = invoice.custom_mpesa_reconciled_payments[0]
		self.assertEqual(child.mpesa_c2b_payment_register, row.name)
		self.assertEqual(child.transid, row.transid)
		self.assertEqual(child.amount, 100)
		self.assertEqual(child.msisdn, "254711111111")
		self.assertEqual(child.mode_of_payment, "Cash")

		# The register row is left untouched -- consumption is deferred
		# until the invoice is actually submitted.
		row.reload()
		self.assertEqual(row.docstatus, 0)
		self.assertFalse(row.payment_entry)

	def test_already_consumed_row_is_rejected(self):
		invoice = self._draft_invoice()
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		# Select + finalize it once (auto_submit=1 submits the invoice and
		# immediately consumes the register row).
		process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=row.name,
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=1,
		)
		row.reload()
		self.assertEqual(row.docstatus, 1)

		other_invoice = self._draft_invoice()
		other_invoice.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			process_mpesa(
				doctype="Sales Invoice",
				invoice_name=other_invoice.name,
				customer=self.customer,
				mpesa_payments=row.name,
				mode_of_payment="Cash",
				auto_save=1,
				auto_submit=0,
			)

		other_invoice.reload()
		self.assertEqual(len(other_invoice.payments), 0)
		self.assertEqual(len(other_invoice.custom_mpesa_reconciled_payments), 0)

	def test_customer_mismatch_is_rejected(self):
		invoice = self._draft_invoice(customer=self.customer)
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		with self.assertRaises(frappe.ValidationError):
			process_mpesa(
				doctype="Sales Invoice",
				invoice_name=invoice.name,
				customer=self.other_customer,
				mpesa_payments=row.name,
				mode_of_payment="Cash",
				auto_save=1,
				auto_submit=0,
			)

		invoice.reload()
		self.assertEqual(len(invoice.payments), 0)
		row.reload()
		self.assertEqual(row.docstatus, 0)

	def test_auto_submit_zero_keeps_invoice_and_register_unconsumed(self):
		invoice = self._draft_invoice()
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=row.name,
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=0,
		)

		invoice.reload()
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(len(invoice.payments), 0)

		row.reload()
		self.assertEqual(row.docstatus, 0)
		self.assertFalse(row.payment_entry)

	def test_auto_submit_one_finalizes_reconciliation(self):
		"""Exact payment (invoice 100, one 100 receipt): the receipt's Payment
		Entry is minted, taken as an advance for the full 100, the invoice
		submits fully paid, and the register row is consumed pointing at that
		same entry (no separate excess-credit entry -- there is nothing left
		unallocated)."""
		invoice = self._draft_invoice(rate=100)
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		result = process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=row.name,
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=1,
		)

		self.assertTrue(result["submitted"])
		# Exact pay -> no overpaid excess -> no unallocated remainder reported.
		self.assertEqual(result["mpesa_reconciliation"], [])

		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(flt(invoice.total_advance), 100)

		row.reload()
		self.assertEqual(row.docstatus, 1)
		child = invoice.custom_mpesa_reconciled_payments[0]
		self.assertEqual(row.payment_entry, child.payment_entry)
		self.assertTrue(child.payment_entry)
		pe = frappe.get_doc("Payment Entry", child.payment_entry)
		self.assertEqual(pe.docstatus, 1)
		self.assertEqual(flt(pe.unallocated_amount), 0)

	def test_duplicate_register_row_name_in_same_call_is_rejected(self):
		invoice = self._draft_invoice()
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		with self.assertRaises(frappe.ValidationError):
			process_mpesa(
				doctype="Sales Invoice",
				invoice_name=invoice.name,
				customer=self.customer,
				mpesa_payments=f"{row.name},{row.name}",
				mode_of_payment="Cash",
				auto_save=1,
				auto_submit=0,
			)

		invoice.reload()
		self.assertEqual(len(invoice.payments), 0)
		row.reload()
		self.assertEqual(row.docstatus, 0)

	def test_auto_save_zero_is_rejected(self):
		# auto_save=0 is not implemented (process_mpesa always saves the
		# invoice); a caller passing 0 expecting some no-op/preview mode must
		# get a clear error instead of a silent real save.
		invoice = self._draft_invoice()
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		with self.assertRaises(frappe.ValidationError):
			process_mpesa(
				doctype="Sales Invoice",
				invoice_name=invoice.name,
				customer=self.customer,
				mpesa_payments=row.name,
				mode_of_payment="Cash",
				auto_save=0,
				auto_submit=0,
			)

		invoice.reload()
		self.assertEqual(len(invoice.payments), 0)
		row.reload()
		self.assertEqual(row.docstatus, 0)

	def test_submit_draft_invoice_finalizes_deferred_mpesa_reconciliation(self):
		"""End-to-end regression for the real POS checkout path: select M-Pesa
		payments on a draft (auto_submit=0), then finalize via
		submit_draft_invoice (as PaymentDialog.tsx's c2b flow does, with
		data=None). Allocation (minting the receipt's Payment Entry, taking it
		as an advance) and register consumption must happen here, not in
		process_mpesa.
		"""
		invoice = self._draft_invoice(rate=100)
		invoice.insert(ignore_permissions=True)
		row = self._make_c2b_payment(amount=100)

		process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=row.name,
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=0,
		)
		row.reload()
		self.assertEqual(row.docstatus, 0)

		result = submit_draft_invoice(invoice.name, data=None)

		self.assertTrue(result["success"])
		# Exact pay -> no unallocated remainder, so the key is omitted.
		self.assertNotIn("mpesa_reconciliation", result)

		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(flt(invoice.total_advance), 100)

		row.reload()
		self.assertEqual(row.docstatus, 1)
		child = invoice.custom_mpesa_reconciled_payments[0]
		self.assertEqual(row.payment_entry, child.payment_entry)
		self.assertTrue(child.payment_entry)
		self.assertEqual(frappe.db.get_value("Payment Entry", child.payment_entry, "docstatus"), 1)

	def test_overpayment_creates_unallocated_customer_credit(self):
		"""Regression for the reported bug: invoice total 100, M-Pesa payments
		totalling 130 (60 + 70). Both receipts mint their own submitted Payment
		Entry; the invoice takes 60 then 40 as advances to reach its 100
		payable, and the leftover 30 stays unallocated on row_b's own entry --
		a real, reusable customer credit tied to the receipt that brought it
		in, not cash "change", not a negative outstanding_amount, and not a
		separate excess-credit Payment Entry.
		"""
		invoice = self._draft_invoice(rate=100)
		invoice.insert(ignore_permissions=True)
		row_a = self._make_c2b_payment(amount=60, msisdn="254733333333")
		row_b = self._make_c2b_payment(amount=70, msisdn="254744444444")

		process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=f"{row_a.name},{row_b.name}",
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=0,
		)

		result = submit_draft_invoice(invoice.name, data=None)
		self.assertTrue(result["success"])

		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(flt(invoice.total_advance), 100)
		self.assertEqual(flt(invoice.change_amount or 0), 0)

		row_a.reload()
		row_b.reload()
		self.assertEqual(row_a.docstatus, 1)
		self.assertEqual(row_b.docstatus, 1)

		children = {c.mpesa_c2b_payment_register: c for c in invoice.custom_mpesa_reconciled_payments}
		pe_a = frappe.get_doc("Payment Entry", children[row_a.name].payment_entry)
		pe_b = frappe.get_doc("Payment Entry", children[row_b.name].payment_entry)
		self.assertEqual(row_a.payment_entry, pe_a.name)
		self.assertEqual(row_b.payment_entry, pe_b.name)
		self.assertEqual(flt(pe_a.paid_amount), 60)
		self.assertEqual(flt(pe_a.unallocated_amount), 0, "row_a's receipt was fully used")
		self.assertEqual(flt(pe_b.paid_amount), 70)
		self.assertEqual(
			flt(pe_b.unallocated_amount), 30, "the overpaid excess sits on row_b's own entry"
		)

		# Exactly one reported remainder, for the receipt that straddled the
		# cap -- no separate excess-credit Payment Entry is created.
		self.assertEqual(len(result["mpesa_reconciliation"]), 1)
		recon = result["mpesa_reconciliation"][0]
		self.assertEqual(flt(recon["excess_amount"]), 30)
		self.assertEqual(recon["payment_entry"], pe_b.name)
		self.assertEqual(recon["register"], row_b.name)
		self.assertEqual(pe_b.docstatus, 1)
		self.assertEqual(pe_b.payment_type, "Receive")
		self.assertEqual(pe_b.party, self.customer)
		# 40 of pe_b's 70 was applied to the invoice as a reference; the rest
		# (30) is the reported, still-unallocated excess -- not a second entry.
		self.assertEqual(len(pe_b.references), 1)
		self.assertEqual(pe_b.references[0].reference_name, invoice.name)
		self.assertEqual(flt(pe_b.references[0].allocated_amount), 40)

		# The overflowing traceability row is linked to its own entry, not a
		# new one.
		invoice.reload()
		linked = {
			c.mpesa_c2b_payment_register: c.excess_payment_entry
			for c in invoice.custom_mpesa_reconciled_payments
			if c.excess_payment_entry
		}
		self.assertEqual(linked, {row_b.name: pe_b.name})

	def test_three_same_mode_receipts_show_one_mode_in_invoice_list(self):
		"""Three M-Pesa receipts reconciled onto one invoice all land under the
		same mode of payment. Each mints its own submitted Payment Entry and is
		taken as a `Sales Invoice Advance` in full (300 invoice, 3x100 receipts
		-> no excess); the invoice's own `payments` table keeps only the one
		zero-amount placeholder row for "Cash" that ERPNext requires, and the
		three advance rows carry the real money. `get_sales_invoices` --
		which feeds Invoice History and Closing Shift -- reads both tables via
		`_batch_fetch_payment_methods`/`klik_pos.api.payment_rows.
		advance_payment_rows`; it used to assume a row count above one meant a
		genuine split across modes and joined the raw rows into
		"Cash/Cash/Cash". That string no longer equals any Mode of Payment
		name, so the till's mode filter (strict equality against the dropdown)
		silently dropped every multi-receipt same-mode sale. It must instead
		dedupe to the bare mode, "Cash".
		"""
		invoice = self._draft_invoice(rate=300)
		invoice.insert(ignore_permissions=True)
		rows = [
			self._make_c2b_payment(amount=100, msisdn=f"25470000020{i}") for i in range(1, 4)
		]

		result = process_mpesa(
			doctype="Sales Invoice",
			invoice_name=invoice.name,
			customer=self.customer,
			mpesa_payments=",".join(r.name for r in rows),
			mode_of_payment="Cash",
			auto_save=1,
			auto_submit=1,
		)
		self.assertTrue(result["submitted"])
		# Exact pay across all three receipts -> no overpaid excess.
		self.assertEqual(result["mpesa_reconciliation"], [])

		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.total_advance), 300)

		from klik_pos.api.sales_invoice import _batch_fetch_payment_methods

		merged = _batch_fetch_payment_methods([invoice.name])[invoice.name]
		self.assertEqual(len(merged), 3, "three advance rows, one per receipt")
		self.assertEqual({m["mode_of_payment"] for m in merged}, {"Cash"})
		self.assertEqual(
			sorted(m["reference_no"] for m in merged),
			sorted(r.transid for r in rows),
			"each advance row must carry its own transid",
		)

		listing = get_sales_invoices(skip_opening_entry_filter=True, search=invoice.name)
		self.assertTrue(listing["success"])
		matches = [inv for inv in listing["data"] if inv["name"] == invoice.name]
		self.assertEqual(len(matches), 1)
		self.assertEqual(
			matches[0]["mode_of_payment"],
			"Cash",
			"three same-mode rows must dedupe to the bare mode, not join into "
			"a repeated string that no longer matches the Mode of Payment filter",
		)
