"""The audit finds the money shapes that should never exist, and only those."""

import frappe

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
		if frappe.get_meta("Sales Invoice").has_field("custom_sale_type"):
			frappe.db.set_value("Sales Invoice", invoice.name, "custom_sale_type", "Cash", update_modified=False)
			key = "short_paid_cash_sale"
		else:
			key = "owing_pos_sale_check_by_hand"
		self.assertIn(invoice.name, self._names(key))

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

	def test_audit_writes_nothing(self):
		before = frappe.db.sql("SELECT COUNT(*) FROM `tabVersion`")[0][0]
		run()
		self.assertEqual(frappe.db.sql("SELECT COUNT(*) FROM `tabVersion`")[0][0], before)
