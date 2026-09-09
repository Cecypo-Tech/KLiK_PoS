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

from unittest.mock import patch

import frappe
from erpnext.accounts.doctype.pos_profile.test_pos_profile import make_pos_profile
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.mpesa import (
	_allocate_receipts_before_submit,
	_ensure_receipt_payment_entries,
	_finalize_mpesa_reconciliation,
	_manual_reconciliation,
	process_mpesa,
)
from klik_pos.api.sales_invoice import (
	QUEUE_STATUSES,
	_get_refundable_cash,
	_mark_invoice_queued,
	create_partial_return,
	process_queued_sales_invoice,
	return_sales_invoice,
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

	def _draft(self, rate=100, qty=1, posting_date="2029-06-15"):
		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=1, rate=rate, qty=qty,
			posting_date=posting_date, do_not_save=True,
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

	def test_a_receipt_whose_register_row_is_already_consumed_mints_nothing(self):
		"""A trace row left over from an earlier attempt whose register row has since been
		submitted is stale: minting an entry for it would invent money the receipt has
		already been spent on, and nothing downstream would ever allocate it."""
		receipt = self._receipt(100)
		invoice = self._record(self._draft(), receipt)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "docstatus", 1, update_modified=False)
		entries_before = frappe.db.count("Payment Entry")

		by_register = _ensure_receipt_payment_entries(invoice)

		self.assertEqual(by_register, {})
		self.assertEqual(frappe.db.count("Payment Entry"), entries_before, "no stray entry was minted")

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

	def test_an_outer_reconciliation_guard_is_restored_not_switched_off(self):
		"""The guard is a site global, so the exit must put back what it found. Forcing it
		to '0' inside a caller that had set it - frappe_mpsa_payments' own quick-pay path
		does exactly that around its own register submit - would hand the register back its
		allocation powers mid-flight."""
		frappe.db.set_global("is_manual_reconciliation", "1")
		self.addCleanup(frappe.db.set_global, "is_manual_reconciliation", "0")

		with _manual_reconciliation():
			self.assertEqual(frappe.db.get_global("is_manual_reconciliation"), "1")

		self.assertEqual(frappe.db.get_global("is_manual_reconciliation"), "1")

	def test_a_fully_used_receipt_reports_no_excess(self):
		_invoice, results = self._submit_with(100, self._receipt(100))

		self.assertEqual(results, [])


class TestPartialPaymentGateCountsAdvances(MpesaFirstCase):
	def test_an_invoice_settled_entirely_by_advances_is_not_a_partial_payment(self):
		"""The gate compared paid_amount to the total. With M-Pesa money arriving as
		advances, paid_amount is 0 on a fully paid sale and the till refused it.

		Run against a real POS Profile rather than a bare draft, because that is what makes
		the gate fire at all - and because saving a draft that names one reaches ERPNext's
		set_pos_fields, which rebuilds `payments` from the profile and would take the
		zero-amount mode row with it.
		"""
		# make_pos_profile clears the POS Profile table before inserting; the test
		# transaction puts the site's own profiles back.
		profile = make_pos_profile(company=COMPANY)
		frappe.db.set_value("POS Profile", profile.name, "allow_partial_payment", 0)
		invoice = self._record(self._draft(rate=100), self._receipt(100))
		invoice.pos_profile = profile.name

		_allocate_receipts_before_submit(invoice)
		invoice.reload()

		self.assertEqual(flt(invoice.total_advance), 100.0)
		self.assertEqual(flt(invoice.paid_amount), 0.0, "the gate has nothing but the advance to go on")
		self.assertIn((MODE, 0.0), [(p.mode_of_payment, flt(p.amount)) for p in invoice.payments])

		invoice.submit()  # must not raise PartialPaymentValidationError

		self.assertEqual(invoice.docstatus, 1)


class TestCancellingAConsumedReceipt(MpesaFirstCase):
	"""The receipt may not un-pay a sale that is still standing.

	Klik points the consumed register row at the Payment Entry it minted, which finally
	gives frappe_mpsa_payments' own on_cancel something to cancel. Cancelling the row
	therefore cancels an entry allocated to a live invoice, and ERPNext deletes that
	invoice's advance rows on the way out: the sale silently reverts to unpaid with no
	trace of what happened.
	"""

	def _settled(self, rate=100):
		receipt = self._receipt(rate, "254700000701")
		invoice = self._record(self._draft(rate=rate), receipt)
		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		_finalize_mpesa_reconciliation(invoice, summary)
		invoice.reload()
		return invoice, frappe.get_doc("Mpesa C2B Payment Register", receipt.name)

	def test_a_receipt_allocated_to_a_live_sale_refuses_to_be_cancelled(self):
		invoice, row = self._settled()
		entry = invoice.custom_mpesa_reconciled_payments[0].payment_entry

		with self.assertRaises(frappe.ValidationError):
			row.cancel()

		self.assertEqual(frappe.db.get_value("Payment Entry", entry, "docstatus"), 1)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Payment Entry Reference",
					{"parent": entry, "reference_name": invoice.name},
					"allocated_amount",
				)
			),
			100.0,
			"the entry is still paying the invoice",
		)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0.0)

	def test_the_receipt_cancels_once_the_sale_it_paid_is_cancelled(self):
		invoice, row = self._settled()

		invoice.cancel()
		row.reload()
		row.cancel()

		self.assertEqual(row.docstatus, 2)


class TestReturningAnAdvanceSettledSale(MpesaFirstCase):
	"""Refundable cash is money that came through the payments table, and no more.

	An M-Pesa sale holds none: the money is on a Payment Entry, and the mode row on the
	invoice carries 0. Reading the refund ceiling as grand_total - outstanding made every
	such sale look like a till full of cash, so a return handed the customer money the
	drawer never took and posted a second M-Pesa movement to pay for it.
	"""

	def _settled(self, rate=100, qty=1, receipt=None):
		# Today, not the module's 2029: a return posts on nowdate() and ERPNext refuses one
		# that predates the invoice it returns.
		draft = self._draft(rate=rate, qty=qty, posting_date=frappe.utils.nowdate())
		invoice = self._record(draft, receipt or self._receipt(rate * qty, "254700000601"))
		summary = _allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		_finalize_mpesa_reconciliation(invoice, summary)
		invoice.reload()
		return invoice

	def _bank_gl(self, voucher):
		return frappe.db.sql(
			"select count(*) from `tabGL Entry` where voucher_no=%s and account=%s and is_cancelled=0",
			(voucher, BANK_ACCOUNT),
		)[0][0]

	def test_an_advance_settled_sale_holds_no_refundable_cash(self):
		invoice = self._settled()

		self.assertEqual(flt(invoice.total_advance), 100.0)
		self.assertEqual(flt(invoice.outstanding_amount), 0.0)
		self.assertEqual(flt(_get_refundable_cash(invoice, invoice)), 0.0)

	def test_a_full_return_credits_the_note_instead_of_paying_out(self):
		invoice = self._settled()

		result = return_sales_invoice(invoice.name)

		self.assertTrue(result.get("success"), result.get("message"))
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([flt(p.amount) for p in credit.payments if flt(p.amount)], [], "no cash went back")
		self.assertEqual(flt(credit.paid_amount), 0.0)
		self.assertEqual(self._bank_gl(credit.name), 0, "the return posts no M-Pesa movement")
		self.assertEqual(flt(abs(credit.outstanding_amount)), 100.0, "the value stays as credit-note balance")

	def test_a_partial_return_credits_its_share_instead_of_paying_out(self):
		invoice = self._settled(rate=50, qty=2)
		item = invoice.items[0].item_code

		result = create_partial_return(invoice.name, [{"item_code": item, "return_qty": 1}], payment_method=MODE)

		self.assertTrue(result.get("success"), result.get("message"))
		self.assertEqual(flt(result["refunded_amount"]), 0.0)
		self.assertEqual(flt(result["credited_amount"]), 50.0)
		self.assertIsNone(result["payment_method"], "nothing was paid out, so no mode paid it")
		credit = frappe.get_doc("Sales Invoice", result["return_invoice"])
		self.assertEqual([flt(p.amount) for p in credit.payments if flt(p.amount)], [])
		self.assertEqual(self._bank_gl(credit.name), 0)


class TestQueuedCheckoutSurvivesNothing(MpesaFirstCase):
	"""A background checkout that cannot finish must not report success.

	The failure this pins had the worst possible shape: the advances had already zeroed
	the outstanding, so the invoice read Paid while its Payment Entries sat unreconciled
	and the receipts stayed pending. The cashier saw a sale; the books did not have one.
	"""

	def test_a_finalize_failure_fails_the_request_rather_than_posting_a_half_done_sale(self):
		invoice = self._record(self._draft(rate=100), self._receipt(100, "254700000501"))
		_mark_invoice_queued(invoice, frappe.session.user)
		invoice.save(ignore_permissions=True)
		# The worker runs against a draft an earlier request committed, and its failure path
		# rolls back; without a commit here that rollback would take this fixture with it and
		# the test would be measuring its own transaction instead of the handler.
		registers = [c.mpesa_c2b_payment_register for c in invoice.custom_mpesa_reconciled_payments]
		frappe.db.commit()
		self.addCleanup(self._remove_committed, invoice.name, registers)

		with (
			patch(
				"klik_pos.api.mpesa._finalize_mpesa_reconciliation",
				side_effect=Exception("reconciliation exploded"),
			),
			patch("klik_pos.api.sales_invoice._notify_queue_failure"),
		):
			result = process_queued_sales_invoice(invoice.name)

		self.assertFalse(result["success"], "the queue reported a sale it had not posted")
		row = frappe.db.get_value(
			"Sales Invoice", invoice.name, ["queue_status", "docstatus"], as_dict=True
		)
		self.assertEqual(row.queue_status, QUEUE_STATUSES["failed"])
		self.assertEqual(row.docstatus, 0, "no submitted invoice may survive a failed finalize")
		self.assertEqual(
			frappe.db.get_value("Mpesa C2B Payment Register", registers[0], "docstatus"),
			0,
			"the receipt is still there to be sold again",
		)

	def _remove_committed(self, invoice_name, registers):
		"""This test commits, so the class-level rollback can no longer clean up after it."""
		if frappe.db.exists("Sales Invoice", invoice_name):
			invoice = frappe.get_doc("Sales Invoice", invoice_name)
			entries = [c.payment_entry for c in invoice.custom_mpesa_reconciled_payments if c.payment_entry]
			if invoice.docstatus == 1:
				invoice.flags.ignore_permissions = True
				invoice.cancel()
			frappe.delete_doc("Sales Invoice", invoice_name, force=True, ignore_permissions=True)
			for entry in entries:
				if frappe.db.exists("Payment Entry", entry):
					pe = frappe.get_doc("Payment Entry", entry)
					if pe.docstatus == 1:
						pe.flags.ignore_permissions = True
						pe.cancel()
					frappe.delete_doc("Payment Entry", entry, force=True, ignore_permissions=True)
		for register in registers:
			if frappe.db.exists("Mpesa C2B Payment Register", register):
				frappe.delete_doc(
					"Mpesa C2B Payment Register", register, force=True, ignore_permissions=True
				)
		# Inserted at DB level in setUpClass, so removed the same way.
		frappe.db.delete("Mpesa Settings", {"business_shortcode": self.shortcode})
		frappe.db.commit()


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
