"""The till offers only customer groups a customer can be saved under.

ERPNext refuses a Group-type Customer Group ("Cannot select a Group type Customer Group"), yet
the new-customer form defaulted to "All Customer Groups" and listed every group node.
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import get_customer_groups


def _offered(profile_groups=()):
	profile = SimpleNamespace(customer_groups=[SimpleNamespace(customer_group=g) for g in profile_groups])
	with patch("klik_pos.api.customer.get_current_pos_profile", return_value=profile):
		result = get_customer_groups()
	return [g["name"] for g in result["data"]]


class TestCustomerGroupsOffered(FrappeTestCase):
	def test_no_group_node_is_offered(self):
		offered = _offered()

		self.assertTrue(offered)
		self.assertNotIn("All Customer Groups", offered)
		self.assertFalse(frappe.get_all("Customer Group", filters={"name": ["in", offered], "is_group": 1}))

	def test_a_profile_group_node_offers_its_leaves(self):
		leaves = frappe.get_all("Customer Group", filters={"parent_customer_group": "All Customer Groups", "is_group": 0}, pluck="name")

		offered = _offered(["All Customer Groups"])

		self.assertTrue(set(leaves) <= set(offered))
		self.assertNotIn("All Customer Groups", offered)
