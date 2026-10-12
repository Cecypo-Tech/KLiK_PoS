"""A queued till sale over the customer's credit limit is refused before it takes a number.

Allparts INV-00224: background submission saved the invoice (number taken) and queued it;
ERPNext checks the credit limit only on submit, in the worker, where nothing rolls back.
The sale sat as a Failed draft. The checkout now runs the check first, so it aborts, rolls
back and the cashier holds the order (a Sales Order, no invoice number) instead.
"""

import inspect
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.api.sales_invoice import _refuse_crossing_credit_limit

CUSTOMER_MODULE = "erpnext.selling.doctype.customer.customer"


def _sale(outstanding, **values):
	return frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": "SULTAN AUTO MASTERS",
			"company": "Allparts Castings Limited",
			"outstanding_amount": outstanding,
			"items": [{"item_code": "X", "qty": 1}],
			**values,
		}
	)


def _account(owing, limit=120000):
	"""The customer's books, and a cashier who is not a credit controller."""
	return (
		patch(f"{CUSTOMER_MODULE}.get_credit_limit", return_value=limit),
		patch(f"{CUSTOMER_MODULE}.get_customer_outstanding", return_value=owing),
		patch.object(frappe, "get_roles", return_value=[]),
	)


class TestRefuseCrossingCreditLimit(FrappeTestCase):
	def _check(self, doc, owing, limit=120000):
		frappe.clear_messages()
		a, b, c = _account(owing, limit)
		with a, b, c:
			_refuse_crossing_credit_limit(doc)

	def test_a_sale_that_crosses_the_limit_is_refused_and_says_hold(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			self._check(_sale(55000), owing=110600)
		self.assertIn("Credit limit has been crossed", str(caught.exception))
		self.assertIn("Hold the order", str(caught.exception))
		# The till shows the first _server_messages entry, not the exception text.
		messages = [m.get("message") for m in frappe.local.message_log]
		self.assertEqual(len(messages), 1, messages)
		self.assertIn("Hold the order", messages[0])

	def test_these_pass(self):
		cases = {
			"under the limit": (_sale(5000), 110600),
			"no limit": (_sale(55000), 110600, 0),
			"a return": (_sale(-55000, is_return=1), 130000),
			"items from a delivery note": (
				_sale(55000, items=[{"item_code": "X", "qty": 1, "delivery_note": "DN-1"}]),
				110600,
			),
		}
		for case, (doc, owing, *limit) in cases.items():
			with self.subTest(case):
				self._check(doc, owing, *limit)

	def test_the_queued_branch_checks_before_the_invoice_is_saved(self):
		source = inspect.getsource(sales_invoice._queue_sales_invoice)
		queued = source[source.index("if enable_background_submission:") :]
		self.assertLess(
			queued.index("_refuse_crossing_credit_limit(doc)"),
			queued.index("doc.save("),
			"checked after the save, a refused sale has already taken its number",
		)
