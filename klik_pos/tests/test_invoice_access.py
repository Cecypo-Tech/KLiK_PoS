"""Who may open an invoice.

get_invoice_details was open to guests and loaded the invoice with no permission check,
so anyone who could reach the site could read any invoice - customer, tax ID, amounts -
by name. And Invoice History held a cashier to their own invoices only in the list: the
detail page opened anyone's, by URL or from a customer's invoice list.

An invoice now opens for a logged-in user with read permission, and then only if it is
theirs or their till (custom_allow_viewing_other_cashiers) lets its users read each
other's. The till decides for managers too; a manager who needs everyone's invoices is
given a till that allows it. The customer invoice list follows the same rule, so it never
lists an invoice that will not open.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.api.sales_invoice import _may_read_invoice, get_invoice_details, get_sales_invoices


def _till(allow, name="Test Till"):
	return patch.object(
		sales_invoice,
		"get_current_pos_profile",
		return_value=frappe._dict({"name": name, "custom_allow_viewing_other_cashiers": allow}),
	)


def _inv(owner, till="Test Till"):
	return frappe._dict({"owner": owner, "pos_profile": till})


class TestTheRule(FrappeTestCase):
	"""_may_read_invoice on its own, so the rule is covered on any site."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_my_own_invoice_opens_on_any_till(self):
		with _till(0, name="Elsewhere"):
			self.assertTrue(_may_read_invoice(_inv("Administrator")))

	def test_another_cashier_s_invoice_needs_the_flag(self):
		with _till(0):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com")))
		with _till(1):
			self.assertTrue(_may_read_invoice(_inv("someone@example.com")))

	def test_another_cashier_s_invoice_from_another_till_never_opens(self):
		"""The list only ever shows the current till's invoices; opening follows it."""
		with _till(1):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", till="Other Till")))

	def test_with_no_till_only_my_own(self):
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			self.assertTrue(_may_read_invoice(_inv("Administrator")))
			self.assertFalse(_may_read_invoice(_inv("someone@example.com")))


def _invoice_owned(by_me):
	me = frappe.session.user
	return frappe.db.get_value(
		"Sales Invoice", {"owner": me if by_me else ["!=", me], "docstatus": 1}, "name"
	)


class TestNotOpenToGuests(FrappeTestCase):
	def test_invoice_endpoints_are_whitelisted_but_not_for_guests(self):
		for method in (get_invoice_details, get_sales_invoices):
			self.assertIn(method, frappe.whitelisted, method.__name__)
			self.assertNotIn(method, frappe.guest_methods, method.__name__)

	def test_a_user_without_read_permission_is_refused(self):
		name = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name")
		if not name:
			self.skipTest("no submitted Sales Invoice on this site")
		email = "no-invoice-access@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": "No Access", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with _till(1):
				result = get_invoice_details(name)
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "forbidden")
		self.assertNotIn("data", result)


class TestARefusalIsNotAnError(FrappeTestCase):
	def test_refused_invoice_says_why_and_logs_nothing(self):
		fake = MagicMock(owner="someone@example.com", pos_profile="Test Till")
		frappe.set_user("Administrator")
		before = frappe.db.count("Error Log")
		with _till(0), patch.object(sales_invoice.frappe, "get_doc", return_value=fake):
			result = get_invoice_details("SINV-FAKE")
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "forbidden")
		self.assertIn("another cashier", result["error"])
		self.assertEqual(frappe.db.count("Error Log"), before)


class TestTheTillDecides(FrappeTestCase):
	"""Run as Administrator, a System Manager: the flag binds managers too."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.mine = _invoice_owned(by_me=True)
		self.theirs = _invoice_owned(by_me=False)
		if not (self.mine and self.theirs):
			self.skipTest("needs submitted invoices by Administrator and by someone else")

	def test_another_cashier_s_invoice_does_not_open_on_a_closed_till(self):
		with _till(0):
			result = get_invoice_details(self.theirs)
		self.assertFalse(result["success"])
		self.assertNotIn("data", result)

	def test_another_cashier_s_invoice_opens_where_the_till_allows_it(self):
		till = frappe.db.get_value("Sales Invoice", self.theirs, "pos_profile")
		with _till(1, name=till):
			self.assertTrue(get_invoice_details(self.theirs)["success"])

	def test_my_own_invoice_always_opens(self):
		with _till(0):
			self.assertTrue(get_invoice_details(self.mine)["success"])

	def test_with_no_till_resolvable_only_my_own_open(self):
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			self.assertFalse(get_invoice_details(self.theirs)["success"])
			self.assertTrue(get_invoice_details(self.mine)["success"])


class TestCustomerListFollowsTheTill(FrappeTestCase):
	def _sql_for(self, **kwargs):
		captured = []
		real = frappe.db.sql

		def spy(query, values=None, *a, **kw):
			captured.append(str(query))
			return real(query, values, *a, **kw)

		with patch("frappe.db.sql", side_effect=spy):
			result = get_sales_invoices(limit=1, **kwargs)
		return result, " ".join(captured)

	def test_customer_list_is_held_to_my_invoices_on_a_closed_till(self):
		with _till(0):
			_, sql = self._sql_for(surface="customer", search="x")
		self.assertIn("si.owner = ", sql)

	def test_customer_list_shows_everyone_s_where_the_till_allows_it(self):
		with _till(1):
			_, sql = self._sql_for(surface="customer", search="x")
		self.assertNotIn("si.owner = ", sql)


class TestNoTillResolvable(FrappeTestCase):
	def test_history_with_no_till_answers_rather_than_crashing(self):
		"""pos_doc was left unbound when the profile lookup raised."""
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			result = get_sales_invoices(limit=1, surface="history", skip_opening_entry_filter=True)
		self.assertTrue(result["success"], result.get("error"))
