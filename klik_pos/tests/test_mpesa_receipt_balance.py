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


class TestDrawDown(ReceiptCase):
	def test_second_sale_draws_what_the_first_left(self):
		receipt = self._receipt(10048)
		self._sell(3450, receipt)
		self._sell(850, receipt)
		self.assertEqual(flt(_receipt_balance(receipt.name).open_amount), 5748)

	def test_a_draw_larger_than_the_balance_takes_the_balance(self):
		receipt = self._receipt(1000)
		self._sell(700, receipt)
		invoice = self._record(self._draft(rate=500), receipt)
		summary = _allocate_receipts_before_submit(invoice)
		self.assertEqual(flt(summary["allocated_total"]), 300)

	def test_minting_links_the_register_row_at_once(self):
		receipt = self._receipt(500)
		invoice = self._record(self._draft(rate=200), receipt)
		_allocate_receipts_before_submit(invoice)
		self.assertTrue(frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry"))

	def test_a_second_invoice_on_a_minted_but_unsubmitted_receipt_reuses_the_entry(self):
		receipt = self._receipt(500)
		first = self._record(self._draft(rate=200), receipt)
		_allocate_receipts_before_submit(first)
		second = self._record(self._draft(rate=100), receipt)
		_allocate_receipts_before_submit(second)
		self.assertEqual(
			frappe.get_doc("Sales Invoice", first.name).custom_mpesa_reconciled_payments[0].payment_entry,
			frappe.get_doc("Sales Invoice", second.name).custom_mpesa_reconciled_payments[0].payment_entry,
		)
		self.assertEqual(
			frappe.db.count("Payment Entry", {"custom_mpesa_receipt_number": receipt.transid, "docstatus": 1}), 1
		)

	def test_a_receipt_drained_after_the_pick_refuses_the_shortfall(self):
		receipt = self._receipt(1000)
		invoice = self._record(self._draft(rate=800), receipt)  # picked while 1000 was open
		self._sell(900, receipt)  # another till takes 900
		invoice.reload()
		with self.assertRaisesRegex(frappe.ValidationError, f"{receipt.transid}.*a moment ago"):
			_allocate_receipts_before_submit(invoice)

	def test_customer_change_after_pick_is_refused(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		invoice = self._record(self._draft(rate=200), receipt)
		self._switch_customer(invoice, OTHER_CUSTOMER)
		with self.assertRaisesRegex(frappe.ValidationError, f"held by {CUSTOMER}"):
			_allocate_receipts_before_submit(invoice)

	def test_finalise_leaves_an_already_consumed_register_row_alone(self):
		receipt = self._receipt(1000)
		first = self._sell(300, receipt)
		self._sell(200, receipt)
		self.assertEqual(frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "sales_invoice"), first.name)

	def test_cancelling_a_sale_gives_its_amount_back_to_the_receipt(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		second = self._sell(200, receipt)
		second.cancel()
		self.assertEqual(flt(_receipt_balance(receipt.name).open_amount), 700)


PHONE_MODE = "_Test Klik Mpesa Phone"


def _ensure_phone_mode():
	if not frappe.db.exists("Mode of Payment", PHONE_MODE):
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": PHONE_MODE,
				"type": "Phone",
				"accounts": [{"company": COMPANY, "default_account": "_Test Bank - _TC"}],
			}
		).insert(ignore_permissions=True)
	frappe.local._klik_mpesa_modes = None


class TestNoReceiptNoMpesa(ReceiptCase):
	def setUp(self):
		_ensure_phone_mode()

	def _typed(self, amount=100, reference=None):
		invoice = self._draft(rate=amount)
		invoice.set("payments", [{"mode_of_payment": PHONE_MODE, "amount": amount, "custom_reference_text": reference}])
		return invoice

	def _stk(self, status="Completed", amount=100, transaction_id="STKTX1"):
		doc = frappe.get_doc(
			{
				"doctype": "Mpesa Express Request",
				"status": status,
				"amount": amount,
				"transaction_id": transaction_id,
				"phone_number": "254700000001",
			}
		)
		doc.name = f"MEXP-TEST-{frappe.generate_hash(length=8)}"
		doc.db_insert()
		return doc.name

	def test_a_typed_mpesa_amount_is_refused(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt behind it"):
			assert_mpesa_rows_backed(self._typed())

	def test_a_completed_stk_push_backs_the_row(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		assert_mpesa_rows_backed(self._typed(reference=self._stk()))

	def test_a_failed_stk_push_does_not(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt behind it"):
			assert_mpesa_rows_backed(self._typed(reference=self._stk(status="Failed", transaction_id=None)))

	def test_an_stk_push_smaller_than_the_row_does_not(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt behind it"):
			assert_mpesa_rows_backed(self._typed(amount=500, reference=self._stk(amount=100)))

	def test_a_zero_placeholder_row_passes(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		invoice = self._typed()
		invoice.payments[0].amount = 0
		assert_mpesa_rows_backed(invoice)

	def test_a_return_is_exempt(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		invoice = self._typed()
		invoice.is_return = 1
		assert_mpesa_rows_backed(invoice)

	def test_non_mpesa_modes_are_untouched(self):
		from klik_pos.api.mpesa import is_mpesa_mode

		self.assertTrue(is_mpesa_mode(PHONE_MODE))
		self.assertFalse(is_mpesa_mode("Cash"))

	def test_submit_runs_the_check(self):
		invoice = self._typed()
		invoice.save()
		with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt behind it"):
			invoice.submit()

	def test_an_stk_push_already_used_on_another_sale_does_not(self):
		from klik_pos.api.mpesa import assert_mpesa_rows_backed

		req = self._stk()
		first = self._typed(reference=req)
		first.save()
		first.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt behind it"):
			assert_mpesa_rows_backed(self._typed(reference=req))

	def test_search_hides_a_receipt_already_paid_by_stk(self):
		receipt = self._receipt(100)
		paid = self._typed(reference=self._stk(transaction_id=receipt.transid))
		paid.save()
		paid.submit()
		self.assertNotIn(receipt.name, self._search(receipt))


class TestRetry(ReceiptCase):
	def test_a_retry_rebuilds_the_advance_from_what_the_receipt_holds_now(self):
		receipt = self._receipt(1000)
		first = self._record(self._draft(rate=200), receipt)
		_allocate_receipts_before_submit(first)  # an attempt that then failed; its advance was kept
		self._sell(300, receipt)  # meanwhile another sale drew 300
		first.reload()
		summary = _allocate_receipts_before_submit(first)
		first.reload()
		self.assertEqual([flt(a.advance_amount) for a in first.advances], [700])
		self.assertEqual(flt(summary["allocated_total"]), 200)
		first.submit()
		_finalize_mpesa_reconciliation(first, summary)
		self.assertEqual(flt(_receipt_balance(receipt.name).open_amount), 500)

	def test_a_failed_foreground_checkout_leaves_no_half_done_receipt_behind(self):
		from unittest.mock import patch

		from klik_pos.api.sales_invoice import submit_draft_invoice

		receipt = self._receipt(500)
		invoice = self._record(self._draft(rate=200), receipt)
		with patch(
			"klik_pos.api.sales_invoice._enforce_submit_permission", side_effect=frappe.ValidationError("refused")
		):
			result = submit_draft_invoice(invoice.name)

		self.assertFalse(result["success"])
		invoice.reload()
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(invoice.advances, [], "no advance from the failed attempt stays on the draft")
		self.assertIsNone(frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry"))
		self.assertEqual(
			frappe.db.count("Payment Entry", {"custom_mpesa_receipt_number": receipt.transid, "docstatus": 1}), 0
		)


class TestCancelGuard(ReceiptCase):
	def test_a_receipt_cannot_be_cancelled_while_a_later_sale_still_draws_on_it(self):
		receipt = self._receipt(1000)
		first = self._sell(300, receipt)
		second = self._sell(200, receipt)
		first.cancel()  # the sale the register row names is gone; the second still uses the entry
		register = frappe.get_doc("Mpesa C2B Payment Register", receipt.name)
		with self.assertRaisesRegex(frappe.ValidationError, second.name):
			register.cancel()
