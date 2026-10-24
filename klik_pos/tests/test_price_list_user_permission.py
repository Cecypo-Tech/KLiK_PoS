"""The price-list picker on the POS offers only the Price Lists the user is allowed.

A User Permission on Price List restricts the user to those lists, exactly as a Warehouse
User Permission restricts the warehouse picker. A user with no such permission sees every
enabled selling list.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item.pricing import get_selling_price_lists

USER = "price-list-perm@example.com"
ALLOWED = "_Test KLiK PL Allowed"
OTHER = "_Test KLiK PL Other"


class TestPriceListUserPermission(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for name in (ALLOWED, OTHER):
			if not frappe.db.exists("Price List", name):
				frappe.get_doc(
					{"doctype": "Price List", "price_list_name": name, "selling": 1, "currency": "INR"}
				).insert()
			frappe.db.set_value("Price List", name, "enabled", 1)
		if not frappe.db.exists("User", USER):
			frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": "Price List", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("User Permission", {"user": USER, "allow": "Price List"})
		frappe.clear_cache(user=USER)

	def _names(self):
		return [row["name"] for row in get_selling_price_lists()["price_lists"]]

	def test_an_unrestricted_user_sees_every_enabled_selling_list(self):
		frappe.set_user(USER)
		names = self._names()
		self.assertIn(ALLOWED, names)
		self.assertIn(OTHER, names)

	def test_a_restricted_user_sees_only_the_allowed_lists(self):
		frappe.get_doc(
			{"doctype": "User Permission", "user": USER, "allow": "Price List", "for_value": ALLOWED}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=USER)
		frappe.set_user(USER)
		self.assertEqual(self._names(), [ALLOWED])
