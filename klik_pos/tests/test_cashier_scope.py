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


def _fake_get_doc(*fakes):
	"""A frappe.get_doc side_effect that returns a fixed fake for specific
	(doctype, name) pairs given as a flat (doctype, name, fake, ...) sequence, and
	otherwise delegates to the real frappe.get_doc - so frappe.log_error's own
	Error Log lookup (and anything else) keeps working while it is patched in."""
	table = {(fakes[i], fakes[i + 1]): fakes[i + 2] for i in range(0, len(fakes), 3)}
	real_get_doc = frappe.get_doc

	def side_effect(*args, **kwargs):
		doctype = kwargs.get("doctype") if kwargs.get("doctype") is not None else (args[0] if args else None)
		name = kwargs.get("name") if kwargs.get("name") is not None else (args[1] if len(args) > 1 else None)
		if (doctype, name) in table:
			return table[(doctype, name)]
		return real_get_doc(*args, **kwargs)

	return side_effect


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


class TestCollectingFollowsTheRule(FrappeTestCase):
	def test_money_on_account_is_refused_when_restricted(self):
		with _till(0):
			result = payment.create_customer_payment_entry(customer="Walk In", amount=10, mode_of_payment="Cash")
		self.assertFalse(result["success"])
		self.assertIn("manager", result["error"])

	def test_an_allocation_that_leaves_money_on_account_is_refused_when_restricted(self):
		mine = frappe.db.get_value(
			"Sales Invoice",
			{"owner": frappe.session.user, "docstatus": 1, "outstanding_amount": [">", 20]},
			["name", "customer"],
			as_dict=True,
		)
		if not mine:
			self.skipTest("no own invoice with 20+ outstanding")
		with _till(0):
			result = payment.create_customer_payment_entry(
				customer=mine.customer, amount=20, mode_of_payment="Cash",
				allocations=[{"sales_invoice": mine.name, "allocated_amount": 10}],
			)
		self.assertFalse(result["success"])
		self.assertIn("manager", result["error"])

	def test_an_overpayment_with_no_allocated_amount_is_refused_when_restricted(self):
		"""allocated_amount is empty and amount (500) exceeds outstanding (100): what will
		actually be allocated is only 100, so 400 would land on account."""
		invoice = frappe._dict(
			name="SI-overpay", customer="Walk In", docstatus=1, owner=frappe.session.user,
			outstanding_amount=100,
		)
		with _till(0), patch.object(payment.frappe, "get_doc", side_effect=_fake_get_doc("Sales Invoice", "SI-overpay", invoice)), \
			patch.object(payment, "assert_may_collect"):
			result = payment.create_customer_payment_entry(
				customer="Walk In", amount=500, mode_of_payment="Cash", sales_invoice="SI-overpay",
			)
		self.assertFalse(result["success"])
		self.assertIn("manager", result["error"])

	def test_a_rounding_remainder_within_precision_is_accepted_when_restricted(self):
		"""Three lines, each rounded to the cent, land half a cent (0.004) short of the
		payment amount - real money, not a floating-point artefact. The old 0.00001
		tolerance refused this; currency-precision rounding must accept it."""
		rows = [
			{"reference_doctype": "Sales Invoice", "reference_name": "SI-0", "allocated_amount": 33.329},
			{"reference_doctype": "Sales Invoice", "reference_name": "SI-1", "allocated_amount": 33.329},
			{"reference_doctype": "Sales Invoice", "reference_name": "SI-2", "allocated_amount": 33.328},
		]
		with _till(0), patch.object(payment, "_build_allocation_rows", return_value=rows), \
			patch.object(payment, "assert_may_collect"), \
			patch.object(payment, "get_current_pos_opening_entry", side_effect=RuntimeError("stopped-here")):
			result = payment.create_customer_payment_entry(
				customer="Walk In", amount=99.99, mode_of_payment="Cash",
				allocations=[
					{"sales_invoice": "SI-0", "allocated_amount": 33.329},
					{"sales_invoice": "SI-1", "allocated_amount": 33.329},
					{"sales_invoice": "SI-2", "allocated_amount": 33.328},
				],
			)
		self.assertFalse(result["success"])
		self.assertIn("stopped-here", result["error"])

	def test_unallocated_list_shows_only_my_receipts_when_restricted(self):
		sql = TestReadSideFollowsTheRule()._sql_for
		with _till(0), patch.object(payment, "get_current_pos_profile", return_value=frappe._dict(company="Dev Co")):
			text = sql(lambda: payment.get_unallocated_customer_payment_entries(limit=1))
		self.assertIn("pe.owner = ", text)

	def test_reconciling_someone_else_s_payment_entry_is_refused_when_restricted(self):
		pe = frappe._dict(
			name="PE-someone-else", owner="someone-else@example.com", docstatus=1,
			payment_type="Receive", party_type="Customer", party="Walk In", company="Dev Co",
			unallocated_amount=100,
		)
		si = frappe._dict(
			name="SI-mine", customer="Walk In", docstatus=1, company="Dev Co", outstanding_amount=100,
		)

		with _till(0), patch.object(payment, "assert_may_collect"), \
			patch.object(payment.frappe, "get_doc", side_effect=_fake_get_doc(
				"Payment Entry", "PE-someone-else", pe, "Sales Invoice", "SI-mine", si
			)):
			result = payment.reconcile_payment_entry_with_invoice("PE-someone-else", "SI-mine")
		self.assertFalse(result["success"])
		self.assertIn("manager", result["error"])

	def test_reconciling_my_own_payment_entry_is_allowed_when_restricted(self):
		"""It must clear the ownership gate; stop the flow right after with a sentinel
		so the test needs no real Payment Reconciliation."""
		pe = frappe._dict(
			name="PE-mine", owner=frappe.session.user, docstatus=1,
			payment_type="Receive", party_type="Customer", party="Walk In", company="Dev Co",
			unallocated_amount=100,
		)
		si = frappe._dict(
			name="SI-mine", customer="Walk In", docstatus=1, company="Dev Co", outstanding_amount=100,
		)

		with _till(0), patch.object(payment, "assert_may_collect"), \
			patch.object(payment.frappe, "get_doc", side_effect=_fake_get_doc(
				"Payment Entry", "PE-mine", pe, "Sales Invoice", "SI-mine", si
			)), \
			patch.object(payment, "_get_customer_receivable_account", side_effect=RuntimeError("stopped-here")):
			result = payment.reconcile_payment_entry_with_invoice("PE-mine", "SI-mine")
		self.assertFalse(result["success"])
		self.assertIn("stopped-here", result["error"])
