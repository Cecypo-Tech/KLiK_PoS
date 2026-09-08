"""A held order must be visible to the person who held it, and to the till's rules.

Two complaints from customers, one cause each:

1. "The Draft tab shows 0, even my own held orders." `get_held_orders` returned only the
   owner's email, while Invoice History filters on the cashier's *full name* - the identity
   `get_sales_invoices` returns. Every held order failed that comparison, so a cashier
   restricted to their own work saw nothing at all.

2. "custom_allow_viewing_other_cashiers doesn't let held docs be seen." The flag was read
   for invoices and ignored here: held orders were scoped by role alone, so opening a till
   up did nothing for the Draft tab.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.sales_order import _attach_cashier_names, _till_allows_other_cashiers, get_held_orders

COMPANY = "Dev Co"
ITEM = "Consulting"
CUSTOMER = "Walk In"


def _held_order(owner=None):
	so = frappe.new_doc("Sales Order")
	so.customer = CUSTOMER
	so.company = COMPANY
	so.transaction_date = frappe.utils.nowdate()
	so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 1)
	so.append("items", {"item_code": ITEM, "qty": 1, "rate": 10, "delivery_date": so.delivery_date})
	so.insert(ignore_permissions=True)
	values = {"custom_is_klik_held": 1}
	if owner:
		values["owner"] = owner
	frappe.db.set_value("Sales Order", so.name, values, update_modified=False)
	so.reload()
	return so


def _profile(allow):
	return frappe._dict({"name": "_Test POS Profile", "custom_allow_viewing_other_cashiers": allow})


class TestHeldOrderCashierIdentity(FrappeTestCase):
	def test_each_order_carries_the_owner_s_full_name(self):
		"""The regression: Invoice History compares this against the cashier filter."""
		orders = [{"name": "SO-1", "owner": "Administrator"}]

		_attach_cashier_names(orders)

		self.assertEqual(
			orders[0]["cashier_name"], frappe.db.get_value("User", "Administrator", "full_name")
		)

	def test_an_unknown_owner_falls_back_to_the_login_rather_than_blank(self):
		"""A blank cashier would silently match nothing and empty the tab again."""
		orders = [{"name": "SO-1", "owner": "deleted-user@example.com"}]

		_attach_cashier_names(orders)

		self.assertEqual(orders[0]["cashier_name"], "deleted-user@example.com")

	def test_a_row_with_no_owner_is_not_fatal(self):
		orders = [{"name": "SO-1"}]

		_attach_cashier_names(orders)

		self.assertEqual(orders[0]["cashier_name"], "")

	def test_the_listing_itself_reports_full_names(self):
		_held_order()

		result = get_held_orders(skip_opening_entry_filter=True, limit=5)

		self.assertTrue(result["success"], msg=result.get("error"))
		self.assertTrue(all("cashier_name" in row for row in result["data"]))


class TestHeldOrdersHonourTheTillSetting(FrappeTestCase):
	def test_the_flag_is_read_from_the_active_profile(self):
		with patch.object(sales_order, "_get_active_pos_profile", return_value=_profile(1)):
			self.assertTrue(_till_allows_other_cashiers())

		with patch.object(sales_order, "_get_active_pos_profile", return_value=_profile(0)):
			self.assertFalse(_till_allows_other_cashiers())

	def test_a_till_that_cannot_be_resolved_stays_closed(self):
		"""No profile reads as "no", which is how the page behaved before the flag existed."""
		with patch.object(sales_order, "_get_active_pos_profile", side_effect=Exception("no profile")):
			self.assertFalse(_till_allows_other_cashiers())

	def test_an_open_till_shows_another_cashier_s_held_order(self):
		"""The complaint: the flag was on and the Draft tab still showed one cashier's work."""
		other = _held_order(owner="somebody-else@example.com")

		with patch("frappe.get_roles", return_value=["All", "Sales User"]):
			with patch.object(sales_order, "_get_active_pos_profile", return_value=_profile(1)):
				result = get_held_orders(skip_opening_entry_filter=True, limit=200)

		self.assertIn(other.name, [row["name"] for row in result["data"]])

	def test_a_closed_till_still_holds_a_cashier_to_their_own(self):
		other = _held_order(owner="somebody-else@example.com")

		with patch("frappe.get_roles", return_value=["All", "Sales User"]):
			with patch.object(sales_order, "_get_active_pos_profile", return_value=_profile(0)):
				result = get_held_orders(skip_opening_entry_filter=True, limit=200)

		self.assertNotIn(other.name, [row["name"] for row in result["data"]])

	def test_a_cashier_always_sees_their_own_held_order(self):
		"""Whatever the flag says, your own work is yours to see."""
		mine = _held_order()

		with patch("frappe.get_roles", return_value=["All", "Sales User"]):
			with patch.object(sales_order, "_get_active_pos_profile", return_value=_profile(0)):
				result = get_held_orders(skip_opening_entry_filter=True, limit=200)

		self.assertIn(mine.name, [row["name"] for row in result["data"]])
