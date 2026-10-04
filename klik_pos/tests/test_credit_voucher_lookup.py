"""A store-credit voucher is its credit note: the note's number plus the original sale's.

The lookup tells the till what a voucher holds before anything is applied. Both numbers
must match, and every failed lookup answers the same way, so it cannot be used to find out
which credit notes exist.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer_credit import apply_customer_credit, lookup_credit_voucher
from klik_pos.tests.credit_fixtures import COMPANY, make_credit_note, make_simple_invoice

CUSTOMER = "_Test Customer"
NO_MATCH = {"status": "no_match"}


def make_part_cash_credit_note(customer, company, amount, cash):
	"""A return that hands part of its value back in cash, as the till books one: a POS return
	with a negative Cash row, the rest left on the note as credit."""
	invoice = make_simple_invoice(customer, company, amount, paid=True)
	note = make_sales_return(invoice.name)
	note.set("advances", [])
	note.total_advance = 0
	note.is_pos = 1
	# The original owes nothing, so the credit stays on the note itself, not on the original.
	note.update_outstanding_for_self = 1
	note.append("payments", {"mode_of_payment": "Cash", "amount": -cash})
	note.insert()
	note.submit()
	return note


class TestVoucherLookup(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_an_unused_note_is_open_for_its_whole_value(self):
		note = make_credit_note(CUSTOMER, COMPANY, 100)
		result = lookup_credit_voucher(note.name, note.return_against)
		self.assertEqual(result["status"], "open")
		self.assertEqual((result["available"], result["total"]), (100.0, 100.0))
		self.assertEqual(
			(result["note"], result["original"], result["customer"]),
			(note.name, note.return_against, CUSTOMER),
		)

	def test_a_rounded_note_is_open_for_what_it_holds(self):
		# The till rounds a note's total (300.4 -> 300, 300.6 -> 301) and the balance is the
		# rounded figure: an untouched note reads open for it, whichever way it rounded.
		for amount in (300.4, 300.6):
			with self.subTest(amount=amount):
				note = make_credit_note(CUSTOMER, COMPANY, amount)
				rounded, owed = frappe.db.get_value(
					"Sales Invoice", note.name, ["rounded_total", "outstanding_amount"]
				)
				self.assertNotEqual(abs(rounded), amount, "this site does not round totals")
				self.assertEqual(abs(rounded), -owed)
				result = lookup_credit_voucher(note.name, note.return_against)
				self.assertEqual(result["status"], "open")
				self.assertEqual((result["total"], result["available"]), (abs(rounded), abs(rounded)))

	def test_a_part_cash_return_is_open_for_the_credit_it_left(self):
		# 100 comes back and 60 of it goes out in cash: the voucher is the 40 left on the
		# note, and none of that has been spent.
		note = make_part_cash_credit_note(CUSTOMER, COMPANY, 100, cash=60)
		self.assertEqual(frappe.db.get_value("Sales Invoice", note.name, "outstanding_amount"), -40.0)
		result = lookup_credit_voucher(note.name, note.return_against)
		self.assertEqual(result["status"], "open")
		self.assertEqual((result["total"], result["available"]), (40.0, 40.0))

	def test_a_partly_spent_note_says_what_is_left(self):
		note = make_credit_note(CUSTOMER, COMPANY, 100)
		sale = make_simple_invoice(CUSTOMER, COMPANY, 60)
		apply_customer_credit(sale.name, [{"invoice": note.name, "amount": 60}])
		result = lookup_credit_voucher(note.name, note.return_against)
		self.assertEqual(
			(result["status"], result["available"], result["total"]), ("partly_used", 40.0, 100.0)
		)

	def test_a_spent_note_has_nothing_left(self):
		note = make_credit_note(CUSTOMER, COMPANY, 30)
		sale = make_simple_invoice(CUSTOMER, COMPANY, 30)
		apply_customer_credit(sale.name, [{"invoice": note.name, "amount": 30}])
		result = lookup_credit_voucher(note.name, note.return_against)
		self.assertEqual((result["status"], result["available"]), ("used", 0.0))

	def test_a_cancelled_note_says_so(self):
		note = make_credit_note(CUSTOMER, COMPANY, 50)
		note.cancel()
		self.assertEqual(lookup_credit_voucher(note.name, note.return_against)["status"], "cancelled")

	def test_a_wrong_original_and_an_unknown_note_answer_the_same(self):
		note = make_credit_note(CUSTOMER, COMPANY, 50)
		self.assertEqual(lookup_credit_voucher(note.name, "POS-DOES-NOT-EXIST"), NO_MATCH)
		self.assertEqual(lookup_credit_voucher("X-POS-DOES-NOT-EXIST", note.return_against), NO_MATCH)

	def test_numbers_match_ignoring_case_and_spaces(self):
		note = make_credit_note(CUSTOMER, COMPANY, 50)
		result = lookup_credit_voucher(f"  {note.name.lower()} ", f" {note.return_against.lower()}  ")
		self.assertEqual(result["status"], "open")

	def test_a_sale_number_typed_as_the_credit_note_is_no_match(self):
		note = make_credit_note(CUSTOMER, COMPANY, 50)
		self.assertEqual(lookup_credit_voucher(note.return_against, note.return_against), NO_MATCH)

	def test_blank_numbers_are_no_match(self):
		self.assertEqual(lookup_credit_voucher("", ""), NO_MATCH)

	def test_non_text_numbers_are_no_match(self):
		note = make_credit_note(CUSTOMER, COMPANY, 50)
		self.assertEqual(lookup_credit_voucher({"name": note.name}, note.return_against), NO_MATCH)
		self.assertEqual(lookup_credit_voucher(note.name, ["x"]), NO_MATCH)
		self.assertEqual(lookup_credit_voucher(note.name, {"x": 1}), NO_MATCH)
