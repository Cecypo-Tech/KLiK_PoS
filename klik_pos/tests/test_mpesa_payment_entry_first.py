"""One M-Pesa receipt is one Payment Entry.

The hybrid flow embedded the paid portion of a receipt on the invoice and put only the
overpaid remainder in a Payment Entry, so a 450 receipt against a 500 sale became 250 on a
Sales Invoice payment row and 200 on a Payment Entry - two vouchers of different types for
one line on the M-Pesa statement - and the register row, once consumed, pointed at nothing.

Now the receipt's whole amount is a Payment Entry, the invoice takes what it needs as an
advance, the remainder stays unallocated on that same entry, and every document names the
others. Fixtures mirror test_process_mpesa: _Test Company, a db_insert-ed Mpesa Settings so
its on_update commit cannot escape the test transaction, and invoices pinned to 2029 so the
site's company-scoped fiscal year does not reject them.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.mpesa import (
	_allocate_receipts_before_submit,
	_ensure_receipt_payment_entries,
	_finalize_mpesa_reconciliation,
	process_mpesa,
)
from klik_pos.tests.mpesa_fixtures import make_c2b_payment

COMPANY = "_Test Company"
CUSTOMER = "_Test Customer"
MODE = "Cheque"  # a stock Bank-type mode; real M-Pesa modes are Bank-type too
BANK_ACCOUNT = "_Test Bank - _TC"


def _ensure_bank_mode():
	if not frappe.db.get_value("Mode of Payment Account", {"company": COMPANY, "parent": MODE}):
		mop = frappe.get_doc("Mode of Payment", MODE)
		mop.append("accounts", {"company": COMPANY, "default_account": BANK_ACCOUNT})
		mop.save()


class MpesaFirstCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.shortcode = f"TSC{frappe.generate_hash(length=6).upper()}"
		settings = frappe.get_doc(
			{
				"doctype": "Mpesa Settings",
				"payment_gateway_name": f"Test Mpesa Gateway {frappe.generate_hash(length=6)}",
				"company": COMPANY,
				"business_shortcode": cls.shortcode,
			}
		)
		settings.db_insert()
		_ensure_bank_mode()

	def _draft(self, rate=100):
		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=1, rate=rate,
			posting_date="2029-06-15", do_not_save=True,
		)
		invoice.set_posting_time = 1
		invoice.posting_time = "10:00:00"
		invoice.set("payments", [])
		invoice.insert(ignore_permissions=True)
		return invoice

	def _receipt(self, amount, msisdn="254700000001"):
		return make_c2b_payment(company=COMPANY, shortcode=self.shortcode, amount=amount, msisdn=msisdn)

	def _record(self, invoice, *receipts):
		process_mpesa(
			doctype="Sales Invoice", invoice_name=invoice.name, customer=CUSTOMER,
			mpesa_payments=",".join(r.name for r in receipts), mode_of_payment=MODE,
			auto_save=1, auto_submit=0,
		)
		invoice.reload()
		return invoice


class TestOnePaymentEntryPerReceipt(MpesaFirstCase):
	def test_each_recorded_receipt_gets_a_submitted_payment_entry_for_its_full_amount(self):
		invoice = self._record(self._draft(rate=500), self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))

		by_register = _ensure_receipt_payment_entries(invoice)

		self.assertEqual(len(by_register), 2)
		for child in invoice.custom_mpesa_reconciled_payments:
			pe = frappe.get_doc("Payment Entry", by_register[child.mpesa_c2b_payment_register])
			self.assertEqual(pe.docstatus, 1)
			self.assertEqual(flt(pe.paid_amount), flt(child.amount), "the whole receipt, not the capped part")
			self.assertEqual(flt(pe.unallocated_amount), flt(child.amount), "nothing allocated yet")
			self.assertEqual(pe.reference_no, child.transid)
			self.assertEqual(pe.custom_mpesa_receipt_number, child.transid)
			self.assertEqual(pe.custom_mpesa_phone_number, child.msisdn)
			self.assertEqual(pe.custom_is_created_from_klik, 1)
			self.assertEqual(child.payment_entry, pe.name)

	def test_the_payment_entry_is_stamped_with_the_invoice_s_shift(self):
		invoice = self._record(self._draft(), self._receipt(100))
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_pos_opening_entry", "POS-OPE-TEST-STAMP", update_modified=False)
		invoice.reload()

		pe_name = next(iter(_ensure_receipt_payment_entries(invoice).values()))

		self.assertEqual(frappe.db.get_value("Payment Entry", pe_name, "custom_pos_opening_entry"), "POS-OPE-TEST-STAMP")

	def test_calling_twice_reuses_the_entry_rather_than_minting_another(self):
		"""A checkout retry after a failed submit must not turn one receipt into two credits."""
		invoice = self._record(self._draft(), self._receipt(100))

		first = _ensure_receipt_payment_entries(invoice)
		invoice.save(ignore_permissions=True)
		invoice.reload()
		second = _ensure_receipt_payment_entries(invoice)

		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count("Payment Entry", {"reference_no": invoice.custom_mpesa_reconciled_payments[0].transid, "docstatus": 1}), 1)

	def test_a_register_row_that_already_has_an_entry_is_reused(self):
		"""The register may already carry payment_entry (a retry that got further last time)."""
		receipt = self._receipt(100)
		invoice = self._record(self._draft(), receipt)
		existing = next(iter(_ensure_receipt_payment_entries(invoice).values()))
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "payment_entry", existing, update_modified=False)
		for child in invoice.custom_mpesa_reconciled_payments:
			child.payment_entry = None

		again = _ensure_receipt_payment_entries(invoice)

		self.assertEqual(again[receipt.name], existing)


class TestAllocationBeforeSubmit(MpesaFirstCase):
	def test_receipts_fill_the_payable_total_in_order_and_the_rest_stays_on_the_entry(self):
		"""500 sale, receipts 250 then 450: 250 + 250 allocated, 200 left on the second entry."""
		invoice = self._record(self._draft(rate=500), self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))

		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()

		self.assertEqual(flt(summary["received_total"]), 700.0)
		self.assertEqual(flt(summary["allocated_total"]), 500.0)
		allocated = [(row.reference_name, flt(row.allocated_amount), flt(row.advance_amount)) for row in invoice.advances]
		self.assertEqual([a[1] for a in allocated], [250.0, 250.0])
		self.assertEqual([a[2] for a in allocated], [250.0, 450.0], "advance_amount is the receipt, allocated is what this invoice took")
		self.assertEqual(flt(invoice.total_advance), 500.0)
		self.assertEqual(flt(invoice.outstanding_amount), 0.0)
		second = invoice.custom_mpesa_reconciled_payments[1]
		self.assertEqual(flt(second.allocated_amount), 250.0)
		self.assertEqual(flt(summary["by_register"][second.mpesa_c2b_payment_register]["excess"]), 200.0)

	def test_an_overpaid_receipt_leaves_its_excess_unallocated_on_its_own_entry(self):
		invoice = self._record(self._draft(rate=200), self._receipt(5000, "254700000301"))

		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()

		self.assertEqual(flt(invoice.advances[0].allocated_amount), 200.0)
		self.assertEqual(flt(invoice.change_amount), 0.0, "M-Pesa never hands back change")
		self.assertEqual(flt(summary["by_register"][invoice.custom_mpesa_reconciled_payments[0].mpesa_c2b_payment_register]["excess"]), 4800.0)

	def test_a_zero_amount_payment_row_keeps_the_mode_on_the_invoice(self):
		"""ERPNext demands at least one payment row on a POS invoice, and every reader of
		'how was this paid' - the list, the detail page, the thermal receipt - looks at the
		payments table. The row carries the mode and no money."""
		invoice = self._record(self._draft(rate=100), self._receipt(100))

		_allocate_receipts_before_submit(invoice)
		invoice.reload()

		rows = [(p.mode_of_payment, flt(p.amount)) for p in invoice.payments]
		self.assertEqual(rows, [(MODE, 0.0)])
		self.assertEqual(flt(invoice.paid_amount), 0.0)

	def test_a_retry_does_not_allocate_the_same_receipt_twice(self):
		"""A checkout that failed after this step re-enters it with last attempt's advances
		still on the draft. The receipt must not be taken twice."""
		invoice = self._record(self._draft(rate=500), self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))
		first = _allocate_receipts_before_submit(invoice)
		invoice.reload()
		advances_after_first = [(a.reference_name, flt(a.allocated_amount)) for a in invoice.advances]

		second = _allocate_receipts_before_submit(invoice)
		invoice.reload()

		self.assertEqual([(a.reference_name, flt(a.allocated_amount)) for a in invoice.advances], advances_after_first)
		self.assertEqual(flt(invoice.total_advance), 500.0)
		self.assertEqual(second["allocated_total"], first["allocated_total"])
		self.assertEqual(second["by_register"], first["by_register"])
		self.assertEqual(len([p for p in invoice.payments if p.mode_of_payment == MODE]), 1, "the zero row is not duplicated either")

	def test_it_refuses_a_submitted_invoice(self):
		invoice = self._record(self._draft(rate=100), self._receipt(100))
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()

		with self.assertRaises(frappe.ValidationError):
			_allocate_receipts_before_submit(invoice)

	def test_nothing_recorded_is_a_no_op(self):
		invoice = self._draft(rate=100)

		summary = _allocate_receipts_before_submit(invoice)

		self.assertEqual(summary["received_total"], 0.0)
		self.assertEqual(invoice.get("advances"), [])


class TestFinalizeAfterSubmit(MpesaFirstCase):
	def _submit_with(self, rate, *receipts):
		invoice = self._record(self._draft(rate=rate), *receipts)
		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		results = _finalize_mpesa_reconciliation(invoice, summary)
		invoice.reload()
		return invoice, results

	def test_the_ledger_is_unchanged_one_voucher_per_receipt(self):
		"""500 sale, 250 + 450: Mpesa account Dr 700, Debtors net Cr 200 - and the invoice
		itself posts no bank movement at all now, only the two entries do."""
		invoice, _ = self._submit_with(500, self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))
		pes = [c.payment_entry for c in invoice.custom_mpesa_reconciled_payments]

		bank_dr = frappe.db.sql(
			"select coalesce(sum(debit),0) from `tabGL Entry` where voucher_no in %(v)s and account=%(a)s and is_cancelled=0",
			{"v": tuple(pes), "a": BANK_ACCOUNT},
		)[0][0]
		invoice_bank = frappe.db.sql(
			"select count(*) from `tabGL Entry` where voucher_no=%s and account=%s", (invoice.name, BANK_ACCOUNT)
		)[0][0]

		self.assertEqual(flt(bank_dr), 700.0)
		self.assertEqual(invoice_bank, 0)
		self.assertEqual(flt(invoice.outstanding_amount), 0.0)
		self.assertEqual(flt(frappe.db.get_value("Payment Entry", pes[1], "unallocated_amount")), 200.0)

	def test_register_rows_are_consumed_and_point_at_both_documents(self):
		receipt = self._receipt(100)
		invoice, _ = self._submit_with(100, receipt)

		row = frappe.db.get_value(
			"Mpesa C2B Payment Register", receipt.name,
			["docstatus", "payment_entry", "sales_invoice", "customer", "submit_payment"], as_dict=True,
		)
		self.assertEqual(row.docstatus, 1)
		self.assertEqual(row.payment_entry, invoice.custom_mpesa_reconciled_payments[0].payment_entry)
		self.assertEqual(row.sales_invoice, invoice.name)
		self.assertEqual(row.customer, CUSTOMER)
		self.assertEqual(row.submit_payment, 0, "the register must not mint a second entry")

	def test_the_excess_is_reported_the_way_the_dialog_reads_it(self):
		invoice, results = self._submit_with(200, self._receipt(5000, "254700000301"))

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["mode_of_payment"], MODE)
		self.assertEqual(flt(results[0]["excess_amount"]), 4800.0)
		self.assertEqual(flt(results[0]["unallocated_amount"]), 4800.0)
		self.assertEqual(results[0]["payment_entry"], invoice.custom_mpesa_reconciled_payments[0].payment_entry)
		self.assertEqual(invoice.custom_mpesa_reconciled_payments[0].excess_payment_entry, results[0]["payment_entry"])

	def test_auto_reconcile_cannot_grab_the_excess_on_the_way_through(self):
		"""With auto_reconcile_c2b on, the register's on_submit FIFO-allocates any
		unallocated funds to the customer's other outstanding invoices. The 4,800 excess
		must still be sitting on its entry afterwards, not silently paying old debts."""
		frappe.db.set_value("Mpesa Settings", {"business_shortcode": self.shortcode}, "auto_reconcile_c2b", 1)
		frappe.clear_cache()
		other = create_sales_invoice(company=COMPANY, customer=CUSTOMER, rate=1000, posting_date="2029-06-10")

		_invoice, results = self._submit_with(200, self._receipt(5000, "254700000301"))

		self.assertEqual(flt(frappe.db.get_value("Payment Entry", results[0]["payment_entry"], "unallocated_amount")), 4800.0)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", other.name, "outstanding_amount")), 1000.0)
		self.assertEqual(frappe.db.get_global("is_manual_reconciliation"), "0", "the guard is released")

	def test_a_fully_used_receipt_reports_no_excess(self):
		_invoice, results = self._submit_with(100, self._receipt(100))

		self.assertEqual(results, [])


class TestPartialPaymentGateCountsAdvances(MpesaFirstCase):
	def test_an_invoice_settled_entirely_by_advances_is_not_a_partial_payment(self):
		"""The gate compared paid_amount to the total. With M-Pesa money arriving as
		advances, paid_amount is 0 on a fully paid sale and the till refused it."""
		profile = frappe.db.get_value("POS Profile", {"company": COMPANY}, "name")
		if not profile:
			self.skipTest("no POS Profile for _Test Company on this site")
		frappe.db.set_value("POS Profile", profile, "allow_partial_payment", 0)
		invoice = self._record(self._draft(rate=100), self._receipt(100))
		invoice.pos_profile = profile
		_allocate_receipts_before_submit(invoice)
		invoice.reload()

		invoice.submit()  # must not raise PartialPaymentValidationError

		self.assertEqual(invoice.docstatus, 1)


class TestCancellation(MpesaFirstCase):
	def test_cancelling_the_invoice_returns_the_money_to_the_entry(self):
		"""Under the old flow the invoice's bank GL reversed and the register still said
		'used'; 500 real shillings were on nobody's books. Now the entry simply becomes
		unallocated again - the customer's credit, still tied to the receipt."""
		invoice = self._record(self._draft(rate=500), self._receipt(250, "254700000201"), self._receipt(450, "254700000202"))
		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		_finalize_mpesa_reconciliation(invoice, summary)
		invoice.reload()
		pes = [c.payment_entry for c in invoice.custom_mpesa_reconciled_payments]

		invoice.cancel()

		self.assertEqual([flt(frappe.db.get_value("Payment Entry", p, "unallocated_amount")) for p in pes], [250.0, 450.0])
		self.assertEqual([frappe.db.get_value("Payment Entry", p, "docstatus") for p in pes], [1, 1], "the money stays on the books")

		for child in invoice.custom_mpesa_reconciled_payments:
			row = frappe.db.get_value("Mpesa C2B Payment Register", child.mpesa_c2b_payment_register, ["docstatus", "sales_invoice"], as_dict=True)
			self.assertEqual(row.docstatus, 1, "the receipt's record of where it was applied is kept")
			self.assertEqual(row.sales_invoice, invoice.name)

	def test_the_flow_refuses_to_start_on_a_site_that_would_strand_money_on_cancel(self):
		original = frappe.db.get_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice")
		frappe.db.set_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice", 0)
		frappe.clear_cache()
		try:
			invoice = self._record(self._draft(rate=100), self._receipt(100))
			with self.assertRaises(frappe.ValidationError):
				_allocate_receipts_before_submit(invoice)
		finally:
			frappe.db.set_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice", original)
			frappe.clear_cache()
