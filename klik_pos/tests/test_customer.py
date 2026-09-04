from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import check_customer_permission, get_customers


class TestCustomerAPI(FrappeTestCase):
	"""Test cases for Customer API functions"""

	def setUp(self):
		super().setUp()

	def test_get_customers_returns_the_matching_rows(self):
		"""get_customers runs one permission-filtered SQL query and returns its rows.

		This test used to patch frappe.get_all and frappe.get_doc, matching an older
		implementation that fetched names and then loaded each Customer doc. The endpoint
		now runs a single SQL query through apply_sql_permissions, and that path calls
		frappe.get_meta("Customer") — which itself goes through frappe.get_all. Patching
		frappe.get_all globally therefore fed a MagicMock into Frappe's own meta loader and
		the call died with "DocType Customer not found" before reaching any assertion.

		Real rows and narrow, module-scoped patches instead: nothing here mocks a Frappe
		primitive the framework also uses internally.
		"""
		token = frappe.generate_hash(length=10)
		expected = set()
		for label in ("One", "Two"):
			doc = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"GetCustomers {label} {token}",
					"customer_type": "Individual",
				}
			).insert(ignore_permissions=True)
			expected.add(doc.name)
			self.addCleanup(
				frappe.delete_doc, "Customer", doc.name, force=True, ignore_permissions=True
			)

		company = frappe.defaults.get_user_default("Company")
		currency = frappe.get_cached_value("Company", company, "default_currency")

		with (
			patch(
				"klik_pos.api.customer.get_current_pos_profile",
				return_value=MagicMock(custom_business_type="B2C", customer_groups=[]),
			),
			patch(
				"klik_pos.api.customer.get_user_company_and_currency",
				return_value=(company, currency),
			),
			# Loyalty is a separate endpoint with its own tests; it would otherwise pull the
			# whole loyalty program setup into a query-shape test.
			patch("klik_pos.api.customer.get_customer_loyalty_summary", return_value={}),
			patch("frappe.permissions.get_user_permissions", return_value={}),
		):
			result = get_customers(limit=10, start=0, search=token)

		self.assertTrue(result["success"], result.get("error"))
		self.assertEqual({row["name"] for row in result["data"]}, expected)
		self.assertEqual(result["total_count"], 2)

		row = result["data"][0]
		self.assertIn(token, row["customer_name"])
		self.assertEqual(row["customer_type"], "Individual")
		self.assertEqual(row["company_currency"], currency)

	@patch("klik_pos.api.customer.get_current_pos_profile")
	@patch("frappe.permissions.get_user_permissions")
	def test_check_customer_permission_b2c_individual(self, mock_user_permissions, mock_pos_profile):
		"""Test check_customer_permission for B2C business type with Individual customer"""

		# Mock POS profile for B2C
		mock_pos_profile.return_value = MagicMock(custom_business_type="B2C", customer_groups=[])

		mock_user_permissions.return_value = {}

		mock_customer = MagicMock()
		mock_customer.customer_type = "Individual"
		mock_customer.customer_group = "All Customer Groups"

		with patch("frappe.get_doc") as mock_get_doc:
			mock_get_doc.return_value = mock_customer

			result = check_customer_permission("CUST-001")

			# Assertions
			self.assertTrue(result["success"])
			self.assertTrue(result["has_permission"])
			self.assertEqual(result["business_type"], "B2C")
			self.assertEqual(result["customer_name"], "CUST-001")

			# Verify mock calls
			mock_pos_profile.assert_called_once()
			mock_user_permissions.assert_called_once()
			mock_get_doc.assert_called_once_with("Customer", "CUST-001")

	@patch("klik_pos.api.customer.get_current_pos_profile")
	@patch("frappe.permissions.get_user_permissions")
	def test_check_customer_permission_b2c_company_denied(self, mock_user_permissions, mock_pos_profile):
		"""Test check_customer_permission for B2C business type with Company customer (should be denied)"""

		# Mock POS profile for B2C
		mock_pos_profile.return_value = MagicMock(custom_business_type="B2C", customer_groups=[])

		# Mock user permissions (no specific customer permissions)
		mock_user_permissions.return_value = {}

		mock_customer = MagicMock()
		mock_customer.customer_type = "Company"
		mock_customer.customer_group = "All Customer Groups"

		with patch("frappe.get_doc") as mock_get_doc:
			mock_get_doc.return_value = mock_customer

			result = check_customer_permission("CUST-COMPANY-001")

			# Assertions
			self.assertTrue(result["success"])
			self.assertFalse(result["has_permission"])
			self.assertEqual(result["business_type"], "B2C")
			self.assertEqual(result["customer_name"], "CUST-COMPANY-001")

			# Verify mock calls
			mock_pos_profile.assert_called_once()
			mock_user_permissions.assert_called_once()
			mock_get_doc.assert_called_once_with("Customer", "CUST-COMPANY-001")

	@patch("klik_pos.api.customer.get_current_pos_profile")
	@patch("frappe.permissions.get_user_permissions")
	def test_check_customer_permission_user_permissions_denied(self, mock_user_permissions, mock_pos_profile):
		"""Test check_customer_permission when user doesn't have permission to specific customer"""

		mock_pos_profile.return_value = MagicMock(custom_business_type="B2C", customer_groups=[])

		mock_user_permissions.return_value = {"Customer": [{"doc": "CUST-001"}]}

		result = check_customer_permission("CUST-002")

		# Assertions
		self.assertTrue(result["success"])
		self.assertFalse(result["has_permission"])
		self.assertEqual(result["customer_name"], "CUST-002")
		self.assertEqual(result["user_permissions"], 1)

		# Verify mock calls
		mock_pos_profile.assert_called_once()
		mock_user_permissions.assert_called_once()

	@patch("klik_pos.api.customer.get_current_pos_profile")
	def test_check_customer_permission_invalid_customer(self, mock_pos_profile):
		"""Test check_customer_permission with non-existent customer"""

		mock_pos_profile.return_value = MagicMock(custom_business_type="B2C", customer_groups=[])

		with patch("frappe.get_doc") as mock_get_doc:
			mock_get_doc.side_effect = frappe.DoesNotExistError("Customer", "NON-EXISTENT")

			# Call the function
			result = check_customer_permission("NON-EXISTENT")

			# Assertions
			self.assertFalse(result["success"])
			self.assertFalse(result["has_permission"])
			self.assertIn("error", result)

			# Verify mock calls
			mock_pos_profile.assert_called_once()
			mock_get_doc.assert_called_once_with("Customer", "NON-EXISTENT")
