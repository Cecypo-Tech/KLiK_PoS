"""A paid M-Pesa push must reach a sale, once.

Allparts: SO-00369's push paid 1,600 and a day later the draft order was submitted from the
desk - an order, not a sale, so the till treated it as gone and the money reached nothing.
SO-00368's 31,300 was booked by an accountant's Payment Entry that names the receipt only in
reference_no, while the order stayed held: finished at the till, it would be booked twice.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.mpesa import _receipt_balance
from klik_pos.api.mpesa_order import _receipt_used
from klik_pos.overrides.sales_order import refuse_submitting_a_paid_mpesa_order
from klik_pos.tests.test_mpesa_order_checkout import EXPRESS, _order, _push
from klik_pos.tests.test_mpesa_receipt_balance import ReceiptCase


class TestAPaidOrderIsNotSubmittedAsAnOrder(FrappeTestCase):
	def test_an_order_its_push_paid_is_refused(self):
		name = _order()
		_push(name, "Completed")
		with self.assertRaisesRegex(frappe.ValidationError, "finish the sale at the till"):
			refuse_submitting_a_paid_mpesa_order(frappe.get_doc("Sales Order", name))

	def test_an_order_a_push_may_still_pay_is_refused(self):
		name = _order()
		_push(name, "In Progress")
		with self.assertRaisesRegex(frappe.ValidationError, "finish the sale at the till"):
			refuse_submitting_a_paid_mpesa_order(frappe.get_doc("Sales Order", name))

	def test_an_order_whose_pushes_all_failed_may_be_submitted(self):
		name = _order()
		_push(name, "Failed")
		refuse_submitting_a_paid_mpesa_order(frappe.get_doc("Sales Order", name))

	def test_submitting_from_the_desk_goes_through_the_guard(self):
		name = _order()
		_push(name, "Completed")
		with self.assertRaisesRegex(frappe.ValidationError, "finish the sale at the till"):
			frappe.get_doc("Sales Order", name).submit()


class TestTheDeskFinishesWhatTheTillHandsIt(ReceiptCase):
	"""The till sends two cases to the desk; the guard must let the desk finish them."""

	def test_an_order_whose_receipt_the_desk_already_booked_may_be_submitted(self):
		receipt = self._receipt(1000)
		self._sell(1000, receipt)  # the receipt now has an entry
		name = _order()
		push = _push(name, "Completed")
		frappe.db.set_value(EXPRESS, push, "transaction_id", receipt.transid)
		refuse_submitting_a_paid_mpesa_order(frappe.get_doc("Sales Order", name))

	def test_an_order_paid_twice_may_be_submitted(self):
		name = _order()
		_push(name, "Completed")
		_push(name, "Completed")
		refuse_submitting_a_paid_mpesa_order(frappe.get_doc("Sales Order", name))


class TestAReceiptBookedByHandIsUsed(ReceiptCase):
	def test_a_desk_entry_naming_the_receipt_in_reference_no_counts(self):
		receipt = self._receipt(1000)
		self._sell(1000, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		# As SO-00368's: the entry names the receipt only in reference_no, the register rows
		# are cancelled and link nothing.
		frappe.db.set_value("Payment Entry", pe, "custom_mpesa_receipt_number", None, update_modified=False)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, {"payment_entry": None, "docstatus": 2}, update_modified=False)
		push = _push("SO-TEST-STRANDED", "Completed")
		frappe.db.set_value(EXPRESS, push, "transaction_id", receipt.transid)
		self.assertEqual(_receipt_used(push), receipt.transid)

	def test_a_desk_refund_naming_the_receipt_is_used_but_never_sale_money(self):
		receipt = self._receipt(1000)
		self._sell(300, receipt)
		pe = frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry")
		# The receipt's entry turned into a refund: money paid out, not in.
		frappe.db.set_value("Payment Entry", pe, {"payment_type": "Pay", "custom_mpesa_receipt_number": None}, update_modified=False)
		frappe.db.set_value("Mpesa C2B Payment Register", receipt.name, {"payment_entry": None, "docstatus": 0}, update_modified=False)
		self.assertEqual(_receipt_balance(receipt.name).state, "unusable")
		push = _push("SO-TEST-REFUND", "Completed")
		frappe.db.set_value(EXPRESS, push, "transaction_id", receipt.transid)
		self.assertEqual(_receipt_used(push), receipt.transid)


class TestReceiptLookupsAreIndexed(FrappeTestCase):
	def test_both_receipt_number_columns_get_an_index(self):
		# Every receipt the till lists is looked up by number; unindexed, each one scans
		# every Payment Entry on the site.
		from klik_pos.patches.v16_0 import add_receipt_number_indexes

		add_receipt_number_indexes.execute()
		indexed = {
			row[0]
			for row in frappe.db.sql(
				"""SELECT COLUMN_NAME FROM information_schema.STATISTICS
				WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tabPayment Entry' AND SEQ_IN_INDEX = 1"""
			)
		}
		self.assertIn("reference_no", indexed)
		self.assertIn("custom_mpesa_receipt_number", indexed)
