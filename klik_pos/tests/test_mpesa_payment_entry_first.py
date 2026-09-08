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
