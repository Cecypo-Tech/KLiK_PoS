"""Regression coverage for the shared total_spent/total_orders/last_visit SQL fragments.

get_customers (list view), get_customer_statistics, and get_customer_account_summary must
all agree on a customer's total spent. Before this, get_customers and get_customer_statistics
summed grand_total (transaction currency) over POS-only invoices, while
get_customer_account_summary summed base_grand_total (company currency) over every channel —
three different numbers for one customer. They now share total_spent_sql/total_orders_sql/
last_visit_sql from customer_summary.py.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import get_customer_statistics, get_customers
from klik_pos.api.customer_summary import get_customer_account_summary

COMPANY = "Dev Co"
ITEM = "Consulting"


def _make_customer(name):
	if frappe.db.exists("Customer", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_invoice(customer, rate, qty=1, is_return=0, return_against=None, pos_opening_entry=None):
	# For a return, pass a negative qty with the original positive rate — grand_total/
	# base_grand_total come out negative, matching how the app books returns.
	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.company = COMPANY
	si.is_pos = 0
	si.is_return = is_return
	si.return_against = return_against
	if pos_opening_entry:
		si.custom_pos_opening_entry = pos_opening_entry
	si.append("items", {"item_code": ITEM, "qty": qty, "rate": rate})
	si.insert(ignore_permissions=True)
	si.submit()
	return si


class TestCustomerTotalsAgree(FrappeTestCase):
	def test_back_office_invoice_counts_toward_total_spent(self):
		"""A non-POS (back-office) invoice must not be invisible to total_spent — the old
		custom_pos_opening_entry filter dropped it entirely."""
		customer = _make_customer("Totals Consistency Customer")
		_make_invoice(customer, rate=1000, pos_opening_entry=None)

		stats = get_customer_statistics(customer)
		self.assertTrue(stats["success"])
		self.assertEqual(frappe.utils.flt(stats["data"]["total_spent"], 2), 1000.0)
		self.assertEqual(stats["data"]["total_orders"], 1)

		summary = get_customer_account_summary(customer)
		self.assertEqual(frappe.utils.flt(summary["net_revenue"], 2), 1000.0)

	def test_return_nets_into_total_spent_without_double_subtracting(self):
		customer = _make_customer("Totals Consistency Return Customer")
		sale = _make_invoice(customer, rate=1000)
		_make_invoice(customer, rate=1000, qty=-1, is_return=1, return_against=sale.name)

		stats = get_customer_statistics(customer)
		self.assertEqual(frappe.utils.flt(stats["data"]["total_spent"], 2), 0.0)
		# The return itself is not counted as a second order.
		self.assertEqual(stats["data"]["total_orders"], 1)

	def test_get_customers_list_total_spent_matches_get_customer_statistics(self):
		customer = _make_customer("Totals Consistency List Customer")
		_make_invoice(customer, rate=750)

		stats = get_customer_statistics(customer)

		result = get_customers(limit=500, start=0, search="Totals Consistency List Customer")
		self.assertTrue(result["success"])
		row = next(r for r in result["data"] if r["name"] == customer)
		self.assertEqual(
			frappe.utils.flt(row["custom_total_spent"], 2),
			frappe.utils.flt(stats["data"]["total_spent"], 2),
		)
