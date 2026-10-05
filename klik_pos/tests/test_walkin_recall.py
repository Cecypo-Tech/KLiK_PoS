"""A returning walk-in gives only their phone: the till recalls the name and PIN from their last sale."""

import random

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import get_customers, get_walkin_details_by_phone

NAME, PHONE = "custom_walkin_customer_name", "custom_walkin_phone"


class TestWalkinRecall(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		if not frappe.db.has_column("Sales Invoice", PHONE):
			self.skipTest("no walk-in fields on this site")
		self.older, self.newer = reversed(
			frappe.get_all("Sales Invoice", filters={"docstatus": 1}, pluck="name", order_by="creation desc", limit=2)
		)
		self.digits = "7" + "".join(random.choices("0123456789", k=8))

	def _sale(self, invoice, phone, name=None, tax_id=None):
		frappe.db.set_value("Sales Invoice", invoice, {PHONE: phone, NAME: name, "tax_id": tax_id}, update_modified=False)

	def test_the_newest_sale_for_the_number_wins_whatever_its_format(self):
		self._sale(self.older, f"0{self.digits}", "Old Name", "A000000000Z")
		self._sale(self.newer, f"+254{self.digits}", "New Name", "B111111111Y")

		for typed in (f"0{self.digits}", f"254{self.digits}", f"+254 {self.digits[:3]} {self.digits[3:]}"):
			with self.subTest(typed=typed):
				self.assertEqual(
					get_walkin_details_by_phone(typed), {"name": "New Name", "tax_id": "B111111111Y"}
				)

	def test_a_blank_on_the_newest_sale_is_filled_from_an_older_one(self):
		self._sale(self.older, f"0{self.digits}", "Old Name", "A000000000Z")
		self._sale(self.newer, f"0{self.digits}", "New Name", None)

		self.assertEqual(get_walkin_details_by_phone(f"0{self.digits}"), {"name": "New Name", "tax_id": "A000000000Z"})

	def test_a_number_saved_with_spaces_or_dashes_is_found(self):
		self._sale(self.newer, f"0{self.digits[:3]} {self.digits[3:6]}-{self.digits[6:]}", "Spaced Name")

		self.assertEqual(get_walkin_details_by_phone(f"+254{self.digits}"), {"name": "Spaced Name"})

	def test_an_unknown_or_short_number_recalls_nothing(self):
		self.assertEqual(get_walkin_details_by_phone(f"0{self.digits}"), {})
		self.assertEqual(get_walkin_details_by_phone("0712"), {})


class TestCustomerListShowsTheTown(FrappeTestCase):
	def test_a_row_carries_its_primary_address_city(self):
		row = frappe.db.sql(
			"""SELECT c.name, a.city FROM `tabCustomer` c JOIN `tabAddress` a ON a.name = c.customer_primary_address
			WHERE c.disabled = 0 AND IFNULL(a.city, '') != '' LIMIT 1""",
			as_dict=True,
		)
		if not row:
			self.skipTest("no customer with a primary address city")
		rows = {r["name"]: r for r in get_customers(limit=100, search=row[0].name)["data"]}
		self.assertEqual(rows[row[0].name]["city"], row[0].city)
