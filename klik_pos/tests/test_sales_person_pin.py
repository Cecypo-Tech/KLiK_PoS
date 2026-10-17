"""A PIN set on a Sales Person is the one the till accepts.

The pos_pin field once went missing: desk's "Set PIN" wrote to nothing, said it worked, and
every PIN at the till came back "Invalid PIN".
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_person import verify_pin


class TestSalesPersonPin(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.profile = frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="name", limit=1)[0]
		sp = frappe.get_doc(
			{"doctype": "Sales Person", "sales_person_name": "PIN Test Rep", "is_group": 0, "enabled": 1}
		).insert(ignore_permissions=True)
		cls.sp = sp.name
		frappe.get_doc(
			{
				"doctype": "POS Profile Sales Person",
				"parent": cls.profile,
				"parenttype": "POS Profile",
				"parentfield": "custom_sales_person",
				"sales_person": cls.sp,
				"enabled": 1,
			}
		).db_insert()
		sp.pos_pin = "4821"
		sp.save(ignore_permissions=True)

	def test_set_pin_is_stored(self):
		self.assertEqual(frappe.get_doc("Sales Person", self.sp).get_password("pos_pin"), "4821")

	def test_right_pin_verifies(self):
		out = verify_pin("4821", "pin-test-device", pos_profile=self.profile)
		self.assertTrue(out["success"], out)
		self.assertEqual(out["salesperson"], self.sp)

	def test_wrong_pin_refused(self):
		self.assertFalse(verify_pin("0000", "pin-test-device", pos_profile=self.profile)["success"])
