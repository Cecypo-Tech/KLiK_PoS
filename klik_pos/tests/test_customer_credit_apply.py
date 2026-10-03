"""Spending credit: ERPNext's own credit-note reconciliation, driven server-side.

Reconciling a credit note against an invoice books a "Credit Note" adjustment Journal
Entry (what desk Payment Reconciliation does). Both outstandings move; no payment row,
no cash or M-Pesa GL. Cancelling the adjustment JE is the undo.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.customer_credit import (
	apply_customer_credit,
	release_customer_credit,
	validate_allocations,
)
from klik_pos.tests.credit_fixtures import COMPANY, make_credit_note, make_simple_invoice

CUSTOMER = "_Test Customer"


def _outstanding(name):
	return flt(frappe.db.get_value("Sales Invoice", name, "outstanding_amount"), 2)


class TestApply(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = COMPANY

	def test_partial_credit_settles_both_sides(self):
		note = make_credit_note(CUSTOMER, self.company, 100)
		sale = make_simple_invoice(CUSTOMER, self.company, 60)
		result = apply_customer_credit(sale.name, [{"invoice": note.name, "amount": 60}])
		self.assertEqual(flt(result["applied"], 2), 60.0)
		self.assertEqual(_outstanding(sale.name), 0.0)
		self.assertEqual(_outstanding(note.name), -40.0)
		self.assertTrue(result["journal_entries"])

	def test_release_restores_both_sides(self):
		note = make_credit_note(CUSTOMER, self.company, 100)
		sale = make_simple_invoice(CUSTOMER, self.company, 60)
		apply_customer_credit(sale.name, [{"invoice": note.name, "amount": 60}])
		release_customer_credit(sale.name)
		self.assertEqual(_outstanding(sale.name), 60.0)
		self.assertEqual(_outstanding(note.name), -100.0)

	def test_cancelling_a_spent_note_unwinds_the_payment(self):
		"""No double-spend: ERPNext cancels the adjustment JE with the note, and the
		sale owes its money again - the value is un-spent everywhere, visibly."""
		note = make_credit_note(CUSTOMER, self.company, 100)
		sale = make_simple_invoice(CUSTOMER, self.company, 100)
		result = apply_customer_credit(sale.name, [{"invoice": note.name, "amount": 100}])
		frappe.get_doc("Sales Invoice", note.name).cancel()
		self.assertEqual(_outstanding(sale.name), 100.0)
		for je in result["journal_entries"]:
			self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)


class TestValidation(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = COMPANY

	def _unsaved_sale(self, amount=50):
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": CUSTOMER,
				"company": self.company,
				"items": [{"item_code": "_Test Item", "qty": 1, "rate": amount}],
			}
		)
		doc.set_missing_values()
		doc.run_method("calculate_taxes_and_totals")
		return doc

	def test_more_than_the_note_holds_is_refused(self):
		note = make_credit_note(CUSTOMER, self.company, 30)
		with self.assertRaises(frappe.ValidationError):
			validate_allocations(self._unsaved_sale(), [{"invoice": note.name, "amount": 31}])

	def test_credit_from_another_company_is_refused(self):
		note = make_credit_note(CUSTOMER, self.company, 30)
		sale = self._unsaved_sale()
		sale.company = "_Test Company 1"
		with self.assertRaises(frappe.ValidationError):
			validate_allocations(sale, [{"invoice": note.name, "amount": 10}])

	def test_anothers_note_is_refused(self):
		note = make_credit_note("_Test Customer 2", self.company, 30)
		with self.assertRaises(frappe.ValidationError):
			validate_allocations(self._unsaved_sale(), [{"invoice": note.name, "amount": 10}])

	def test_a_consumed_or_unsubmitted_note_is_refused(self):
		note = make_credit_note(CUSTOMER, self.company, 30)
		spent = make_simple_invoice(CUSTOMER, self.company, 30)
		apply_customer_credit(spent.name, [{"invoice": note.name, "amount": 30}])
		with self.assertRaises(frappe.ValidationError):
			validate_allocations(self._unsaved_sale(), [{"invoice": note.name, "amount": 1}])

	def test_currency_mismatch_is_refused(self):
		note = make_credit_note(CUSTOMER, self.company, 30)
		sale = self._unsaved_sale()
		sale.currency = "USD"
		with self.assertRaises(frappe.ValidationError):
			validate_allocations(sale, [{"invoice": note.name, "amount": 10}])
