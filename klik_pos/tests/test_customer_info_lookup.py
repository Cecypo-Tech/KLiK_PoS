from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import get_customer_info


class TestCustomerInfoLookup(FrappeTestCase):
	"""get_customer_info is handed a Customer ID. ERPNext names a second customer with the same
	name "<name>-1" but keeps its customer_name, so a name-first lookup returned the duplicate:
	its phone, contact and ID, and the POS then saved edits onto it."""

	def make_customer(self, customer_name, mobile_no=""):
		doc = frappe.get_doc(
			{"doctype": "Customer", "customer_name": customer_name, "customer_type": "Company", "mobile_no": mobile_no}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Customer", doc.name, force=True, ignore_permissions=True)
		return doc

	def test_an_id_shared_with_another_customers_name_returns_that_id(self):
		name = f"Lookup Dup {frappe.generate_hash(length=8)}"
		original = self.make_customer(name)
		duplicate = self.make_customer(name)
		self.assertNotEqual(original.name, duplicate.name)
		# Let the duplicate win any lookup by customer_name.
		frappe.db.set_value("Customer", duplicate.name, "modified", frappe.utils.add_days(frappe.utils.now(), 1))

		with (
			patch("klik_pos.api.customer.get_current_pos_profile", return_value=MagicMock(company=None)),
			patch("klik_pos.api.customer.get_party_details", return_value={}) as party_details,
			patch("klik_pos.api.customer.get_customer_loyalty_summary", return_value={}),
		):
			info = get_customer_info(original.name)

		self.assertEqual(info.get("name"), original.name, info)
		self.assertEqual(party_details.call_args.kwargs["party"], original.name)

	def test_returns_the_customers_delivery_personnel(self):
		personnel = frappe.get_doc({"doctype": "Delivery Personnel", "delivery_personnel": "Info Test Courier"}).insert(
			ignore_permissions=True
		)
		self.addCleanup(frappe.delete_doc, "Delivery Personnel", personnel.name, force=True, ignore_permissions=True)
		customer = self.make_customer(f"Delivery {frappe.generate_hash(length=8)}")
		frappe.db.set_value("Customer", customer.name, "custom_delivery_personnel", personnel.name)

		with (
			patch("klik_pos.api.customer.get_current_pos_profile", return_value=MagicMock(company=None)),
			patch("klik_pos.api.customer.get_party_details", return_value={}),
			patch("klik_pos.api.customer.get_customer_loyalty_summary", return_value={}),
		):
			info = get_customer_info(customer.name)

		self.assertEqual(info.get("delivery_personnel"), personnel.name, info)
