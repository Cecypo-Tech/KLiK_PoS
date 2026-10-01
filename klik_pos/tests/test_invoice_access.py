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
from klik_pos.api.sales_invoice import (
	_may_read_invoice,
	_may_read_row,
	get_invoice_details,
	get_sales_invoices,
)


def _till(allow, name="Test Till", company="Test Co"):
	return patch.object(
		sales_invoice,
		"get_current_pos_profile",
		return_value=frappe._dict({"name": name, "company": company, "custom_allow_viewing_other_cashiers": allow}),
	)


def _inv(owner, till="Test Till", company="Test Co"):
	return frappe._dict({"owner": owner, "pos_profile": till, "company": company})


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

	def test_another_cashier_s_invoice_from_another_till_opens_where_the_till_allows_it(self):
		"""The regression (Allparts): the list shows every till's invoices, so a sale rung on
		"Allparts Sales" was listed at "Allparts Cashier" but had no View or Return."""
		with _till(1):
			self.assertTrue(_may_read_invoice(_inv("someone@example.com", till="Other Till")))
		with _till(0):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", till="Other Till")))

	def test_another_company_s_invoice_never_opens(self):
		with _till(1):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", company="Other Co")))

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
		company = frappe.db.get_value("Sales Invoice", self.theirs, "company")
		# Any till of the invoice's company, not only the one it was rung on.
		with _till(1, name="Some Other Till", company=company):
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
		# Everyone's in the till's company, plus one's own anywhere - not one's own only.
		self.assertIn("(si.owner = %s OR si.company = %s)", sql)
		self.assertNotIn("AND si.owner = %s AND", sql.replace("(si.owner = %s OR", ""))


class TestNoTillResolvable(FrappeTestCase):
	def test_history_with_no_till_answers_rather_than_crashing(self):
		"""pos_doc was left unbound when the profile lookup raised."""
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			result = get_sales_invoices(limit=1, surface="history", skip_opening_entry_filter=True)
		self.assertTrue(result["success"], result.get("error"))


class TestRowsSayWhetherTheyOpen(FrappeTestCase):
	def test_rows_follow_the_same_rule_as_opening(self):
		till = frappe._dict({"name": "Test Till", "company": "Test Co", "custom_allow_viewing_other_cashiers": 0})
		self.assertTrue(_may_read_row("me@example.com", "Test Co", "me@example.com", till))
		self.assertFalse(_may_read_row("you@example.com", "Test Co", "me@example.com", till))
		till.custom_allow_viewing_other_cashiers = 1
		self.assertTrue(_may_read_row("you@example.com", "Test Co", "me@example.com", till))
		self.assertFalse(_may_read_row("you@example.com", "Other Co", "me@example.com", till))
		self.assertFalse(_may_read_row("you@example.com", "Test Co", "me@example.com", None))

	def test_history_lists_only_what_opens_where_the_till_allows_others(self):
		"""Another company's invoices were listed - with no View - on a till that allows
		reading other cashiers': 150 such rows on dev."""
		frappe.set_user("Administrator")
		# A till in one company, with another cashier's invoice in a different company.
		elsewhere = frappe.db.get_value(
			"Sales Invoice", {"docstatus": 1, "owner": ["!=", "Administrator"]}, ["name", "company"], as_dict=True
		)
		company = elsewhere and frappe.db.get_value("Company", {"name": ["!=", elsewhere.company]}, "name")
		if not company:
			self.skipTest("needs another cashier's invoice and a second company")
		with _till(1, company=company):
			result = get_sales_invoices(limit=500, skip_opening_entry_filter=True, surface="history")
		self.assertTrue(result["success"], result.get("error"))
		self.assertTrue(result["data"])
		self.assertEqual([r["name"] for r in result["data"] if not r["can_open"]], [])

	def test_every_listed_row_carries_can_open(self):
		frappe.set_user("Administrator")
		with _till(0):
			result = get_sales_invoices(limit=5, skip_opening_entry_filter=True)
		self.assertTrue(result["success"], result.get("error"))
		for row in result["data"]:
			self.assertIn("can_open", row)
