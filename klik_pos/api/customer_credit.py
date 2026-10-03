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


def validate_allocations(invoice_doc, allocations):
	"""Check every row BEFORE the sale submits, so apply cannot fail for business reasons."""
	normalized = []
	total = 0.0
	for row in allocations or []:
		name, amount = row.get("invoice"), flt(row.get("amount"), 2)
		if amount <= 0:
			continue
		note = frappe.db.get_value(
			"Sales Invoice",
			name,
			["name", "customer", "company", "currency", "docstatus", "is_return", "outstanding_amount"],
			as_dict=True,
		)
		if not note or note.docstatus != 1 or not note.is_return:
			frappe.throw(f"{name} is not a submitted credit note.")
		if note.customer != invoice_doc.customer:
			frappe.throw(f"{name} belongs to another customer.")
		if note.company != invoice_doc.company or note.currency != invoice_doc.currency:
			frappe.throw(f"{name} is from another company or currency.")
		available = flt(-note.outstanding_amount, 2)
		if amount > available:
			frappe.throw(f"{name} holds {available}, not {amount}.")
		normalized.append({"invoice": note.name, "amount": amount})
		total += amount
	if total > flt(invoice_doc.grand_total, 2):
		frappe.throw("Credit exceeds the invoice total.")
	return normalized


def apply_customer_credit(invoice_name, allocations):
	"""Reconcile each note against the submitted invoice - the desk tool's own path."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	before = {je.name for je in _adjustment_jes(invoice_name)}
	applied = 0.0
	for row in allocations:
		pr = frappe.new_doc("Payment Reconciliation")
		pr.company = invoice.company
		pr.party_type = "Customer"
		pr.party = invoice.customer
		pr.receivable_payable_account = invoice.debit_to
		pr.get_unreconciled_entries()
		payments = [p.as_dict() for p in pr.payments if p.reference_name == row["invoice"]]
		invoices = [i.as_dict() for i in pr.invoices if i.invoice_number == invoice_name]
		if not payments or not invoices:
			frappe.throw(f"{row['invoice']} no longer holds credit to apply.")
		pr.allocate_entries(frappe._dict({"payments": payments, "invoices": invoices}))
		for a in pr.allocation:
			a.allocated_amount = min(flt(a.allocated_amount, 2), flt(row["amount"], 2))
		pr.reconcile()
		applied += flt(row["amount"], 2)
	return {
		"applied": flt(applied, 2),
		"journal_entries": [je.name for je in _adjustment_jes(invoice_name) if je.name not in before],
	}


def release_customer_credit(invoice_name):
	"""Cancel the adjustment JEs referencing the invoice; both outstandings restore."""
	cancelled = []
	for je in _adjustment_jes(invoice_name):
		frappe.get_doc("Journal Entry", je.name).cancel()
		cancelled.append(je.name)
	return cancelled


def _adjustment_jes(invoice_name):
	"""Submitted Credit Note adjustment JEs with a row referencing the invoice."""
	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"reference_type": "Sales Invoice", "reference_name": invoice_name, "docstatus": 1},
		fields=["parent"],
	)
	names = sorted({r.parent for r in rows})
	return [
		frappe._dict(name=n)
		for n in names
		if frappe.db.get_value("Journal Entry", n, ["voucher_type", "docstatus"]) == ("Credit Note", 1)
	]
