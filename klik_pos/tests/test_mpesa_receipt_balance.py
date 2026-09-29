"""A receipt pays until it runs out: the search, the pick and the allocation all read
what is left on the receipt's Payment Entry, not whether the register row is a draft.
Fixtures follow test_mpesa_payment_entry_first (MpesaFirstCase)."""

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import (
	_allocate_receipts_before_submit,
	_finalize_mpesa_reconciliation,
	_klik_entry_for_transid,
	_receipt_balance,
	get_mpesa_payments,
	process_mpesa,
)
from klik_pos.tests.test_mpesa_payment_entry_first import COMPANY, CUSTOMER, MODE, MpesaFirstCase

OTHER_CUSTOMER = "_Test Customer 1"


class ReceiptCase(MpesaFirstCase):
	def _draft_for(self, customer, rate=100):
		"""A draft for `customer`; the fixture's addresses belong to _Test Customer, so they go."""
		invoice = self._draft(rate=rate)
		if customer != CUSTOMER:
			self._switch_customer(invoice, customer)
		return invoice

	@staticmethod
	def _switch_customer(invoice, customer):
		invoice.customer = customer
		for field in ("customer_address", "address_display", "shipping_address_name", "shipping_address"):
			if invoice.meta.has_field(field):
				invoice.set(field, None)
		invoice.save()

	def _sell(self, rate, *receipts, customer=CUSTOMER):
		"""Pick receipts onto a fresh draft of `rate`, allocate, submit, finalise."""
		invoice = self._draft_for(customer, rate=rate)
		process_mpesa(
			doctype="Sales Invoice", invoice_name=invoice.name, customer=customer,
			mpesa_payments=",".join(r.name for r in receipts), mode_of_payment=MODE,
		)
		invoice.reload()
		summary = _allocate_receipts_before_submit(invoice)
		invoice.submit()
		_finalize_mpesa_reconciliation(invoice, summary)
		invoice.reload()
		return invoice

	def _search(self, receipt, customer=CUSTOMER):
		result = get_mpesa_payments(company=COMPANY, search=receipt.transid, customer=customer)
		return {p["name"]: p for p in result["payments"]}


class TestReceiptBalance(ReceiptCase):
	def test_an_untouched_receipt_is_new_for_its_full_amount(self):
		receipt = self._receipt(1000)
		bal = _receipt_balance(receipt.name)
		self.assertEqual((bal.state, bal.open_amount, bal.payment_entry, bal.held_by), ("new", 1000, None, None))

	def test_a_part_used_receipt_is_open_for_what_its_entry_has_left(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		bal = _receipt_balance(receipt.name)
		self.assertEqual(bal.state, "open")
		self.assertEqual(flt(bal.open_amount), 700)
		self.assertEqual(bal.held_by, CUSTOMER)

	def test_a_used_up_receipt_is_spent(self):
		receipt = self._receipt(300)
		self._sell(300, receipt)
		self.assertEqual(_receipt_balance(receipt.name).state, "spent")

	def test_a_cancelled_register_row_is_unusable(self):
		receipt = self._receipt(300)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "docstatus", 2)
		self.assertEqual(_receipt_balance(receipt.name).state, "unusable")

	def test_a_klik_entry_found_by_receipt_number_is_reused(self):
		receipt = self._receipt(500)
		self._sell(200, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "payment_entry", None)
		self.assertEqual(_klik_entry_for_transid(receipt.transid), pe)
		self.assertEqual(_receipt_balance(receipt.name).payment_entry, pe)


class TestSearch(ReceiptCase):
	def test_search_offers_a_part_used_receipt_at_its_open_amount(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		row = self._search(receipt)[receipt.name]
		self.assertEqual((row["state"], flt(row["open_amount"]), row["selectable"]), ("open", 700, True))
		self.assertEqual(row["used_count"], 1)

	def test_search_drops_a_spent_receipt(self):
		receipt = self._receipt(300)
		self._sell(300, receipt)
		self.assertNotIn(receipt.name, self._search(receipt))

	def test_search_greys_out_another_customers_receipt(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		row = self._search(receipt, customer=OTHER_CUSTOMER)[receipt.name]
		self.assertFalse(row["selectable"])
		self.assertEqual(row["held_by"], CUSTOMER)

	def test_count_includes_open_receipts(self):
		before = get_mpesa_payments(company=COMPANY)["count"]
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		self.assertEqual(get_mpesa_payments(company=COMPANY)["count"], before + 1)


class TestPick(ReceiptCase):
	def test_an_open_receipt_can_be_picked_again(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		invoice = self._draft(rate=200)
		result = process_mpesa(doctype="Sales Invoice", invoice_name=invoice.name, customer=CUSTOMER,
			mpesa_payments=receipt.name, mode_of_payment=MODE)
		self.assertEqual(flt(result["total_amount"]), 700)
		invoice.reload()
		child = invoice.custom_mpesa_reconciled_payments[0]
		self.assertEqual(flt(child.amount), 700)
		self.assertTrue(child.payment_entry)

	def test_a_spent_receipt_is_refused_by_name(self):
		receipt = self._receipt(300)
		self._sell(300, receipt)
		with self.assertRaisesRegex(frappe.ValidationError, f"{receipt.transid}.*nothing left"):
			process_mpesa(doctype="Sales Invoice", invoice_name=self._draft().name, customer=CUSTOMER,
				mpesa_payments=receipt.name, mode_of_payment=MODE)

	def test_another_customers_receipt_is_refused_with_who_holds_it(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		invoice = self._draft_for(OTHER_CUSTOMER)
		with self.assertRaisesRegex(frappe.ValidationError, f"held by {CUSTOMER}"):
			process_mpesa(doctype="Sales Invoice", invoice_name=invoice.name, customer=OTHER_CUSTOMER,
				mpesa_payments=receipt.name, mode_of_payment=MODE)

	def test_the_same_receipt_twice_on_one_invoice_is_refused(self):
		receipt = self._receipt(1000)
		invoice = self._draft(rate=200)
		process_mpesa(doctype="Sales Invoice", invoice_name=invoice.name, customer=CUSTOMER,
			mpesa_payments=receipt.name, mode_of_payment=MODE)
		with self.assertRaisesRegex(frappe.ValidationError, "already on this invoice"):
			process_mpesa(doctype="Sales Invoice", invoice_name=invoice.name, customer=CUSTOMER,
				mpesa_payments=receipt.name, mode_of_payment=MODE)
