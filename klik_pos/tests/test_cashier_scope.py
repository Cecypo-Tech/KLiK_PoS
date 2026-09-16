"""With the till's flag off, a cashier sees and collects only on invoices they rang.

Money owed on anyone else's invoices is for a manager, another till, or the desk. The
customer page's figures, receivables, pay-outstanding list and return list all follow the
invoice list, so a restricted cashier never sees a number made of invoices they cannot open.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import cashier_scope, customer_summary, payment, receivables
from klik_pos.api import sales_invoice as si_api


def _till(allow):
	return patch.object(
		cashier_scope,
		"get_current_pos_profile",
		return_value=frappe._dict({"name": "T", "company": "Dev Co", "custom_allow_viewing_other_cashiers": allow}),
	)


class TestTheRule(FrappeTestCase):
	def test_flag_off_restricts_and_flag_on_does_not(self):
		with _till(0):
			self.assertTrue(cashier_scope.restricted_to_own())
			self.assertEqual(cashier_scope.own_invoice_filter(), {"owner": frappe.session.user})
		with _till(1):
			self.assertFalse(cashier_scope.restricted_to_own())
			self.assertEqual(cashier_scope.own_invoice_filter(), {})

	def test_no_till_restricts(self):
		with patch.object(cashier_scope, "get_current_pos_profile", side_effect=Exception("none")):
			self.assertTrue(cashier_scope.restricted_to_own())

	def test_collecting_on_someone_else_s_invoice_is_refused_when_restricted(self):
		theirs = frappe.db.get_value("Sales Invoice", {"owner": ["!=", frappe.session.user]}, "name")
		if not theirs:
			self.skipTest("no invoice by another user")
		with _till(0), self.assertRaises(frappe.PermissionError):
			cashier_scope.assert_may_collect([theirs])
		with _till(1):
			cashier_scope.assert_may_collect([theirs])


class TestReadSideFollowsTheRule(FrappeTestCase):
	def _sql_for(self, call):
		captured = []
		real = frappe.db.sql

		def spy(query, values=None, *a, **kw):
			captured.append(str(query))
			return real(query, values, *a, **kw)

		with patch("frappe.db.sql", side_effect=spy):
			call()
		return " ".join(captured)

	def test_outstanding_list_is_owner_filtered_when_restricted(self):
		with _till(0), patch.object(payment, "get_current_pos_profile", return_value=frappe._dict(company="Dev Co")):
			sql = self._sql_for(lambda: payment.get_outstanding_sales_invoices(limit=1))
		self.assertIn("si.owner = ", sql)

	def test_account_summary_is_owner_filtered_when_restricted(self):
		customer = frappe.db.get_value("Customer", {}, "name")
		captured = {}
		real = frappe.get_all

		def spy(doctype, *a, **kw):
			if doctype == "Sales Invoice":
				captured.update(kw.get("filters") or {})
			return real(doctype, *a, **kw)

		with _till(0), patch.object(customer_summary.frappe, "get_all", side_effect=spy), \
			patch.object(customer_summary, "_outstanding_for", return_value=0.0):
			customer_summary.get_customer_account_summary(customer)
		self.assertEqual(captured.get("owner"), frappe.session.user)

	def test_receivables_skip_the_ar_engine_and_filter_by_owner_when_restricted(self):
		with _till(0), patch.object(receivables, "get_current_pos_profile", return_value=frappe._dict({"name": "T", "company": "Dev Co"})), \
			patch.object(receivables, "_get_ar_execute", side_effect=AssertionError("AR engine used")), \
			patch.object(receivables, "_degraded_receivables_fallback", return_value={"success": True}) as fallback:
			receivables.get_customer_receivables(customer="Walk In")
		self.assertEqual(fallback.call_args.kwargs.get("owner"), frappe.session.user)

	def test_return_list_is_owner_filtered_when_restricted(self):
		captured = {}
		real = frappe.get_all

		def spy(doctype, *a, **kw):
			if doctype == "Sales Invoice":
				captured.update(kw.get("filters") or {})
			return real(doctype, *a, **kw)

		with _till(0), patch.object(si_api, "_ensure_return_allowed"), \
			patch.object(si_api.frappe, "get_all", side_effect=spy):
			si_api.get_customer_invoices_for_return("Walk In")
		self.assertEqual(captured.get("owner"), frappe.session.user)
