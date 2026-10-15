"""The audit finds the money shapes that should never exist, and only those."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from klik_pos.api.sales_invoice import SITE_SALE_TYPE_FIELD, _site_sale_types
from klik_pos.mpesa_audit import run
from klik_pos.tests.test_mpesa_receipt_balance import ReceiptCase

SINCE = "2029-01-01"  # the fixtures' invoices are dated 2029


class TestMpesaAudit(ReceiptCase):
	def _names(self, key):
		return {r["name"] for r in run(since=SINCE)[key]}

	def test_a_clean_sale_is_not_reported(self):
		receipt = self._receipt(1000)
		invoice = self._sell(800, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		for key, rows in run(since=SINCE).items():
			names = {r["name"] for r in rows}
			self.assertFalse(names & {invoice.name, pe, receipt.name, receipt.transid}, key)

	def test_an_overdrawn_receipt_entry_is_reported(self):
		receipt = self._receipt(1000)
		self._sell(800, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		frappe.db.set_value("Payment Entry", pe, "unallocated_amount", -50, update_modified=False)
		self.assertIn(pe, self._names("overdrawn_receipt"))

	def test_a_pos_sale_left_owing_is_reported(self):
		# CS-02273: submitted with nothing paid.
		invoice = self._sell(800, self._receipt(1000))
		frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 800, update_modified=False)
		if {"Cash", "Credit"} <= _site_sale_types():
			frappe.db.set_value("Sales Invoice", invoice.name, SITE_SALE_TYPE_FIELD, "Cash", update_modified=False)
			key = "short_paid_cash_sale"
		else:
			key = "owing_pos_sale_check_by_hand"
		self.assertIn(invoice.name, self._names(key))

	def test_an_owing_sale_with_no_sale_type_is_left_for_a_person(self):
		# Older, desk or imported POS invoices carry no Cash/Credit; they must not vanish.
		invoice = self._sell(800, self._receipt(1000))
		frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 800, update_modified=False)
		if frappe.get_meta("Sales Invoice").has_field(SITE_SALE_TYPE_FIELD):
			frappe.db.set_value("Sales Invoice", invoice.name, SITE_SALE_TYPE_FIELD, None, update_modified=False)
		self.assertIn(invoice.name, self._names("owing_pos_sale_check_by_hand"))

	def _consumed_outside_klik(self):
		"""A consumed receipt with no entry and no klik trace row, as STK or quick-pay leave it."""
		receipt = self._receipt(1000)
		invoice = self._sell(800, receipt)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, {"payment_entry": None, "sales_invoice": None}, update_modified=False)
		frappe.db.delete("POS Mpesa Reconciled Payment", {"mpesa_c2b_payment_register": receipt.name})
		return receipt, invoice

	def test_a_receipt_consumed_outside_klik_with_no_sale_behind_it_is_reported(self):
		receipt, _ = self._consumed_outside_klik()
		self.assertTrue(self._reported_consumed(receipt))

	def _reported_consumed(self, receipt):
		rows = run(since=frappe.utils.nowdate())["consumed_row_without_entry"]
		return receipt.name in {r["name"] for r in rows}

	def test_a_receipt_named_on_a_sale_s_payment_row_is_not_reported(self):
		# STK push and the M-Pesa app's quick-pay keep the money on the invoice's M-Pesa row.
		receipt, invoice = self._consumed_outside_klik()
		frappe.get_doc({
			"doctype": "Sales Invoice Payment", "parent": invoice.name, "parenttype": "Sales Invoice",
			"parentfield": "payments", "mode_of_payment": "Cash", "amount": 0, "reference_no": receipt.transid,
		}).db_insert()
		self.assertFalse(self._reported_consumed(receipt))

	def test_a_receipt_whose_register_row_names_a_submitted_sale_is_not_reported(self):
		receipt, invoice = self._consumed_outside_klik()
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "sales_invoice", invoice.name, update_modified=False)
		self.assertFalse(self._reported_consumed(receipt))

	def test_an_stk_receipt_whose_request_is_on_a_sale_is_not_reported(self):
		receipt, invoice = self._consumed_outside_klik()
		req = frappe.generate_hash(length=10)
		frappe.db.sql(
			"INSERT INTO `tabMpesa Express Request` (name, transaction_id, status, creation, modified) VALUES (%s, %s, 'Completed', NOW(), NOW())",
			(req, receipt.transid),
		)
		frappe.get_doc({
			"doctype": "Sales Invoice Payment", "parent": invoice.name, "parenttype": "Sales Invoice",
			"parentfield": "payments", "mode_of_payment": "Cash", "amount": 0, "custom_reference_text": req,
		}).db_insert()
		self.assertFalse(self._reported_consumed(receipt))

	def test_the_default_window_leaves_old_history_out(self):
		receipt = self._receipt(1000)
		self._sell(800, receipt)
		frappe.db.set_value(
			"Mpesa C2B Payment Register", receipt.name,
			{"payment_entry": None, "posting_date": add_days(nowdate(), -60)}, update_modified=False,
		)
		self.assertNotIn(receipt.name, {r["name"] for r in run()["consumed_row_without_entry"]})

	def test_two_entries_for_one_receipt_are_reported(self):
		receipt = self._receipt(1000)
		self._sell(800, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		twin = frappe.copy_doc(frappe.get_doc("Payment Entry", pe))
		twin.references = []
		twin.insert(ignore_permissions=True)
		twin.submit()
		frappe.db.set_value("Payment Entry", twin.name, "custom_mpesa_receipt_number", receipt.transid, update_modified=False)
		self.assertIn(receipt.transid, self._names("receipt_with_several_entries"))

	def test_a_consumed_row_whose_entry_is_gone_is_reported(self):
		receipt = self._receipt(1000)
		self._sell(800, receipt)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, "payment_entry", None, update_modified=False)
		# Register rows carry the day they arrived, not the 2029 invoice date.
		rows = run(since=frappe.utils.nowdate())["consumed_row_without_entry"]
		self.assertIn(receipt.name, {r["name"] for r in rows})

	def test_a_return_carrying_the_sale_s_receipt_rows_is_not_over_allocation(self):
		# A return copies the sale's M-Pesa trace rows; the receipt was used once, not twice.
		receipt = self._receipt(1000)
		sale = self._sell(800, receipt)
		stand_in = self._sell(100, self._receipt(100))
		frappe.db.set_value("Sales Invoice", stand_in.name, "is_return", 1, update_modified=False)
		row = frappe.copy_doc(sale.custom_mpesa_reconciled_payments[0])
		row.update({"parent": stand_in.name, "parenttype": "Sales Invoice", "parentfield": "custom_mpesa_reconciled_payments"})
		row.db_insert()
		self.assertNotIn(receipt.name, self._names("receipt_over_allocated_on_invoices"))

	def test_a_receipt_on_two_sales_past_its_amount_is_reported(self):
		receipt = self._receipt(1000)
		sale = self._sell(800, receipt)
		other = self._sell(100, self._receipt(100))
		row = frappe.copy_doc(sale.custom_mpesa_reconciled_payments[0])
		row.update({"parent": other.name, "parenttype": "Sales Invoice", "parentfield": "custom_mpesa_reconciled_payments"})
		row.db_insert()
		self.assertIn(receipt.name, self._names("receipt_over_allocated_on_invoices"))

	def test_each_check_is_capped_at_the_limit(self):
		for _ in range(2):
			receipt = self._receipt(1000)
			self._sell(800, receipt)
			pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
			frappe.db.set_value("Payment Entry", pe, "unallocated_amount", -50, update_modified=False)
		self.assertEqual(len(run(since=SINCE, limit=1)["overdrawn_receipt"]), 1)

	def test_a_site_without_the_receipt_column_is_told_so(self):
		with patch.object(frappe.db, "has_column", return_value=False):
			with self.assertRaisesRegex(frappe.ValidationError, "custom_mpesa_receipt_number"):
				run()

	def test_audit_writes_nothing(self):
		before = frappe.db.sql("SELECT COUNT(*) FROM `tabVersion`")[0][0]
		run()
		self.assertEqual(frappe.db.sql("SELECT COUNT(*) FROM `tabVersion`")[0][0], before)
