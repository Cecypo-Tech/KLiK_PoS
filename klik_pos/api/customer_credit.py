"""A customer's spendable credit, and spending it on an invoice.

Credit is an open credit note: a submitted Sales Invoice return whose outstanding is
negative. Spending it books the same "Credit Note" adjustment Journal Entry that desk
Payment Reconciliation books - ERPNext's own mechanism, nothing parallel to maintain.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.sales_invoice import _is_walkin_customer


@frappe.whitelist()
def get_customer_credit(customer, company, currency=None):
	"""Open credit notes the customer can spend at this company's till.

	`currency` is the currency the till sells in; it defaults to the company's,
	and a caller holding a cart in another currency passes that one instead.
	"""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	if not customer or _is_walkin_customer(customer):
		return {"total": 0.0, "notes": []}
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	rows = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"company": company,
			"currency": currency,
			"docstatus": 1,
			"is_return": 1,
			"outstanding_amount": ["<", 0],
		},
		fields=["name", "posting_date", "outstanding_amount"],
		order_by="posting_date asc, name asc",
	)
	notes = [
		{
			"invoice": r.name,
			"posting_date": str(r.posting_date),
			"available": flt(-r.outstanding_amount, 2),
		}
		for r in rows
	]
	return {"total": flt(sum(n["available"] for n in notes), 2), "notes": notes}
