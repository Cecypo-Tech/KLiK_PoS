"""Who may open an invoice.

get_invoice_details was open to guests and loaded the invoice with no permission check,
so anyone who could reach the site could read any invoice - customer, tax ID, amounts -
by name. And Invoice History held a cashier to their own invoices only in the list: the
detail page opened anyone's, by URL or from a customer's invoice list.

An invoice now opens for a logged-in user with read permission, and then only if it is
theirs or their till (custom_allow_viewing_other_cashiers) lets its users read each
other's. Managers (Express Admin, System Manager, Sales Master Manager, Sales Manager)
open any invoice of their till's company. The customer invoice list follows the same rule, so it never
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


def _sharing(*tills):
	"""Tills selling from the current till's warehouse (the current one included)."""
	return patch.object(sales_invoice, "_tills_sharing_warehouse", return_value=["Test Till", *tills])


def _inv(owner, till="Test Till", company="Test Co", docstatus=1):
	return frappe._dict({"owner": owner, "pos_profile": till, "company": company, "docstatus": docstatus})


def _as_cashier(case):
	"""Run as a cashier: Administrator holds every role, manager ones included."""
	roles = patch("frappe.get_roles", return_value=["All", "Sales User"])
	roles.start()
	case.addCleanup(roles.stop)


class TestTheRule(FrappeTestCase):
	"""_may_read_invoice on its own, so the rule is covered on any site."""

	def setUp(self):
		frappe.set_user("Administrator")
		_as_cashier(self)

	def test_my_own_invoice_opens_on_any_till(self):
		with _till(0, name="Elsewhere"):
			self.assertTrue(_may_read_invoice(_inv("Administrator")))

	def test_another_cashier_s_invoice_needs_the_flag(self):
		with _till(0):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com")))
		with _till(1):
			self.assertTrue(_may_read_invoice(_inv("someone@example.com")))

	def test_another_cashier_s_invoice_from_a_till_on_my_warehouse_opens_where_the_till_allows_it(self):
		"""The regression (Allparts): a sale rung on "Allparts Sales" was listed at "Allparts
		Cashier" - same warehouse - but had no View or Return."""
		with _till(1), _sharing("Other Till"):
			self.assertTrue(_may_read_invoice(_inv("someone@example.com", till="Other Till")))
		with _till(0), _sharing("Other Till"):
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", till="Other Till")))

	def test_a_till_on_another_warehouse_does_not_open(self):
		with _till(1), _sharing():
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", till="Other Till")))

	def test_drafts_follow_the_warehouse_too(self):
		with _till(1), _sharing("Other Till"):
			self.assertTrue(_may_read_invoice(_inv("someone@example.com", till="Other Till", docstatus=0)))
		with _till(1), _sharing():
			self.assertFalse(_may_read_invoice(_inv("someone@example.com", till="Other Till", docstatus=0)))
			self.assertTrue(_may_read_invoice(_inv("Administrator", till="Other Till", docstatus=0)))

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
		company, till = frappe.db.get_value("Sales Invoice", self.theirs, ["company", "pos_profile"])
		if not till:
			self.skipTest("their invoice was rung on no till")
		# Any till selling from the same warehouse, not only the one it was rung on.
		with _till(1, name="Some Other Till", company=company), _sharing(till):
			self.assertTrue(get_invoice_details(self.theirs)["success"])

	def test_my_own_invoice_always_opens(self):
		with _till(0):
			self.assertTrue(get_invoice_details(self.mine)["success"])

	def test_with_no_till_resolvable_only_my_own_open(self):
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			self.assertFalse(get_invoice_details(self.theirs)["success"])
			self.assertTrue(get_invoice_details(self.mine)["success"])


class TestCustomerListFollowsTheTill(FrappeTestCase):
	def setUp(self):
		_as_cashier(self)

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
		with _till(1), _sharing("Other Till"):
			_, sql = self._sql_for(surface="customer", search="x")
		# Everyone's on the tills sharing the warehouse, plus one's own - not one's own only.
		self.assertIn("(si.owner = %s OR (si.company = %s AND si.pos_profile IN (", sql)
		self.assertNotIn("si.owner = %s", sql.replace("(si.owner = %s OR", ""))


class TestNoTillResolvable(FrappeTestCase):
	def test_history_with_no_till_answers_rather_than_crashing(self):
		"""pos_doc was left unbound when the profile lookup raised."""
		with patch.object(sales_invoice, "get_current_pos_profile", side_effect=Exception("no till")):
			result = get_sales_invoices(limit=1, surface="history", skip_opening_entry_filter=True)
		self.assertTrue(result["success"], result.get("error"))


class TestRowsSayWhetherTheyOpen(FrappeTestCase):
	def test_rows_follow_the_same_rule_as_opening(self):
		_as_cashier(self)
		till = frappe._dict({"name": "Test Till", "company": "Test Co", "custom_allow_viewing_other_cashiers": 0})
		self.assertTrue(_may_read_row("me@example.com", "Test Co", "me@example.com", till))
		self.assertFalse(_may_read_row("you@example.com", "Test Co", "me@example.com", till))
		till.custom_allow_viewing_other_cashiers = 1
		shared = ["Test Till", "Other Till"]
		self.assertTrue(_may_read_row("you@example.com", "Test Co", "me@example.com", till, pos_profile="Other Till", shared_tills=shared))
		self.assertFalse(_may_read_row("you@example.com", "Test Co", "me@example.com", till, pos_profile="Far Till", shared_tills=shared))
		self.assertFalse(_may_read_row("you@example.com", "Other Co", "me@example.com", till, pos_profile="Other Till", shared_tills=shared))
		self.assertFalse(_may_read_row("you@example.com", "Test Co", "me@example.com", None))

	def test_history_lists_only_what_opens_where_the_till_allows_others(self):
		"""Another company's invoices were listed - with no View - on a till that allows
		reading other cashiers': 150 such rows on dev. A manager's list is the till's company,
		and every row of it opens."""
		frappe.set_user("Administrator")
		company = frappe.db.get_value(
			"Sales Invoice", {"docstatus": 1, "owner": ["!=", "Administrator"]}, "company"
		)
		if not company or frappe.db.count("Company") < 2:
			self.skipTest("needs another cashier's invoice and a second company")
		with _till(1, company=company):
			result = get_sales_invoices(limit=500, skip_opening_entry_filter=True, surface="history")
		self.assertTrue(result["success"], result.get("error"))
		self.assertTrue(result["data"])
		self.assertTrue(all(r["company"] == company or r["owner"] == "Administrator" for r in result["data"]))
		self.assertEqual([r["name"] for r in result["data"] if not r["can_open"]], [])

	def test_every_listed_row_carries_can_open(self):
		frappe.set_user("Administrator")
		with _till(0):
			result = get_sales_invoices(limit=5, skip_opening_entry_filter=True)
		self.assertTrue(result["success"], result.get("error"))
		for row in result["data"]:
			self.assertIn("can_open", row)


class TestManagersSeeTheWholeCompany(FrappeTestCase):
	"""Allparts: INV-00015, made in the desk from a POS Sales Order, has no till and is not a POS
	sale, so no till rule ever lists or opens it. A manager (by role, not by till) sees every
	invoice of the till's company, wherever and however it was made."""

	def _rule(self, *roles, company="Test Co"):
		with patch("frappe.get_roles", return_value=["All", *roles]), _till(0):
			return _may_read_invoice(_inv("someone@example.com", till=None, company=company))

	def test_each_manager_role_opens_an_invoice_rung_on_no_till(self):
		for role in ("Express Admin", "System Manager", "Sales Master Manager", "Sales Manager"):
			self.assertTrue(self._rule(role), role)

	def test_a_cashier_still_does_not(self):
		self.assertFalse(self._rule("Sales User"))

	def test_not_another_company_s(self):
		self.assertFalse(self._rule("Sales Manager", company="Other Co"))

	def _sql_for(self, *roles, **kwargs):
		captured = []
		real = frappe.db.sql

		def spy(query, values=None, *a, **kw):
			captured.append(str(query))
			return real(query, values, *a, **kw)

		with patch("frappe.get_roles", return_value=["All", *roles]), _till(0), patch("frappe.db.sql", side_effect=spy):
			get_sales_invoices(limit=1, **kwargs)
		return " ".join(captured)

	def test_history_lists_the_whole_company_for_a_manager(self):
		sql = self._sql_for("Sales Master Manager", surface="history", skip_opening_entry_filter=True)
		self.assertIn("(si.owner = %s OR si.company = %s)", sql)
		self.assertNotIn("si.pos_profile", sql)

	def test_history_still_holds_a_cashier(self):
		sql = self._sql_for("Sales User", surface="history", skip_opening_entry_filter=True)
		self.assertIn("si.owner = ", sql)


class TestTheTillIsToldWhoSeesEverything(FrappeTestCase):
	"""Invoice History locks its cashier filter to one's own name unless told otherwise."""

	def test_user_info_says_whether_this_user_sees_every_invoice(self):
		from klik_pos.api.user import get_current_user_info

		with patch("frappe.get_roles", return_value=["All", "Sales User"]):
			self.assertFalse(get_current_user_info()["data"]["can_view_all_invoices"])
		with patch("frappe.get_roles", return_value=["All", "Sales Master Manager"]):
			self.assertTrue(get_current_user_info()["data"]["can_view_all_invoices"])
