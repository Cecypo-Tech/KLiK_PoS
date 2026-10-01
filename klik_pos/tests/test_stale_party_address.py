"""Changing the customer on a held order or a draft must not keep the old customer's address.

ERPNext's set_missing_values keeps a document's billing address even when its customer
changes, and validation then refuses it: "Billing Address does not belong to the <new
customer>". Holding again after switching customer, or finishing a recalled draft for a new
customer, hit it - the old customer's address and contact rode along on the document.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_order import create_held_order

FIRST = "_Test Customer"  # has its own address
SECOND = "_Test Customer 1"  # has a different one
ITEM = "Consulting"


def _payload(customer, **extra):
	return {
		"customer": {"id": customer},
		"items": [{"id": ITEM, "item_code": ITEM, "name": ITEM, "quantity": 1, "price": 100, "uom": "Nos"}],
		"status": "held",
		**extra,
	}


def _addresses_of(customer):
	return set(
		frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
			pluck="parent",
		)
	)


class TestStalePartyAddress(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not (_addresses_of(FIRST) and _addresses_of(SECOND)):
			self.skipTest("needs two customers with addresses of their own")

	def test_holding_again_for_another_customer_takes_their_address(self):
		first = create_held_order(_payload(FIRST))
		self.assertTrue(first["success"], first.get("message"))
		self.assertIn(frappe.db.get_value("Sales Order", first["order_name"], "customer_address"), _addresses_of(FIRST))

		second = create_held_order(_payload(SECOND, held_order_id=first["order_name"]))

		self.assertTrue(second["success"], second.get("message"))
		so = frappe.db.get_value(
			"Sales Order", first["order_name"], ["customer", "customer_address", "contact_person"], as_dict=True
		)
		self.assertEqual(so.customer, SECOND)
		self.assertNotIn(so.customer_address, _addresses_of(FIRST))

	def test_a_recalled_draft_finished_for_another_customer_takes_their_address(self):
		from klik_pos.api.sales_invoice import create_draft_invoice

		draft = create_draft_invoice(_payload(FIRST))
		self.assertTrue(draft["success"], draft.get("message"))
		name = draft["invoice_name"]
		self.assertIn(frappe.db.get_value("Sales Invoice", name, "customer_address"), _addresses_of(FIRST))

		again = create_draft_invoice(_payload(SECOND, draft_invoice_id=name))

		self.assertTrue(again["success"], again.get("message"))
		invoice = frappe.db.get_value("Sales Invoice", name, ["customer", "customer_address"], as_dict=True)
		self.assertEqual(invoice.customer, SECOND)
		self.assertNotIn(invoice.customer_address, _addresses_of(FIRST))

	def test_the_customer_name_follows_the_customer(self):
		first = create_held_order(_payload(FIRST))
		create_held_order(_payload(SECOND, held_order_id=first["order_name"]))
		self.assertEqual(
			frappe.db.get_value("Sales Order", first["order_name"], "customer_name"),
			frappe.db.get_value("Customer", SECOND, "customer_name"),
		)

	def test_holding_again_for_the_same_customer_keeps_their_address(self):
		first = create_held_order(_payload(FIRST))
		address = frappe.db.get_value("Sales Order", first["order_name"], "customer_address")

		again = create_held_order(_payload(FIRST, held_order_id=first["order_name"]))

		self.assertTrue(again["success"], again.get("message"))
		self.assertEqual(frappe.db.get_value("Sales Order", first["order_name"], "customer_address"), address)
