"""Invoice History filters by a From/To date on the server.

The list is paged, so a range picked in the SPA has to reach the query: filtering only
the loaded pages silently misses older invoices.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days

from klik_pos.api.sales_invoice import get_sales_invoices


class TestInvoiceDateRange(FrappeTestCase):
	def setUp(self):
		rows = frappe.get_all(
			"Sales Invoice", fields=["name", "posting_date"], order_by="creation desc", limit=1
		)
		if not rows:
			self.skipTest("no Sales Invoice on this site")
		self.invoice, self.day = rows[0].name, rows[0].posting_date

	def names(self, **kw):
		result = get_sales_invoices(search=self.invoice, surface="dashboard", limit=500, **kw)
		self.assertTrue(result["success"], msg=result.get("error"))
		return [r["name"] for r in result["data"]]

	def test_both_ends_are_inclusive(self):
		self.assertIn(self.invoice, self.names(from_date=str(self.day), to_date=str(self.day)))

	def test_a_range_before_or_after_leaves_it_out(self):
		self.assertNotIn(self.invoice, self.names(to_date=str(add_days(self.day, -1))))
		self.assertNotIn(self.invoice, self.names(from_date=str(add_days(self.day, 1))))

	def test_no_range_is_unbounded(self):
		self.assertIn(self.invoice, self.names())
		self.assertIn(self.invoice, self.names(from_date="", to_date=""))
