"""Listing a customer's spendable credit: open credit notes, oldest first.

Credit = a submitted Sales Invoice return with negative outstanding, same company and
currency as the till will sell in. Walk In credit is never listed - nobody can prove
it is theirs later; the exchange-now flow is the only way to spend it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer_credit import get_customer_credit
from klik_pos.tests.credit_fixtures import COMPANY, make_credit_note

CUSTOMER = "_Test Customer"


class TestListing(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = COMPANY

	def test_an_open_credit_note_is_listed_with_its_value(self):
		note = make_credit_note(CUSTOMER, self.company, 100)
		credit = get_customer_credit(CUSTOMER, self.company, currency=note.currency)
		names = [n["invoice"] for n in credit["notes"]]
		self.assertIn(note.name, names)
		row = next(n for n in credit["notes"] if n["invoice"] == note.name)
		self.assertEqual(row["available"], 100.0)
		self.assertGreaterEqual(credit["total"], 100.0)

	def test_notes_come_oldest_first(self):
		older = make_credit_note(CUSTOMER, self.company, 40, posting_date="2026-01-02")
		newer = make_credit_note(CUSTOMER, self.company, 60, posting_date="2026-06-02")
		credit = get_customer_credit(CUSTOMER, self.company, currency=older.currency)
		names = [n["invoice"] for n in credit["notes"]]
		self.assertLess(names.index(older.name), names.index(newer.name))

	def test_another_companys_note_is_not_listed(self):
		# Same currency on purpose: the company scope alone must exclude it.
		note = make_credit_note(CUSTOMER, self.company, 50)
		credit = get_customer_credit(CUSTOMER, "_Test Company 1", currency=note.currency)
		self.assertNotIn(note.name, [n["invoice"] for n in credit["notes"]])

	def test_a_walkin_customer_has_no_spendable_credit(self):
		from unittest.mock import patch

		from klik_pos.api import customer_credit

		make_credit_note(CUSTOMER, self.company, 70)
		with patch.object(customer_credit, "_is_walkin_customer", return_value=True):
			credit = get_customer_credit(CUSTOMER, self.company)
		self.assertEqual(credit, {"total": 0.0, "notes": []})
