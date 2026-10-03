"""Builders for credit-router tests: a plain submitted invoice and a credit note.

Plain ERPNext documents on purpose - the router must work on credit notes however they
were made (klik return, desk Return button, manual entry).
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

COMPANY = "_Test Company"


def make_simple_invoice(customer, company, amount, posting_date=None, paid=False, item="_Test Item"):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": company,
			"set_posting_time": 1 if posting_date else 0,
			"posting_date": posting_date or frappe.utils.nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": amount}],
		}
	)
	doc.insert()
	doc.submit()
	if paid:
		pe = get_payment_entry("Sales Invoice", doc.name)
		pe.reference_no = doc.name
		pe.reference_date = doc.posting_date
		pe.insert()
		pe.submit()
	return doc


def make_credit_note(customer, company, amount, posting_date=None, item="_Test Item"):
	# The original is paid first: only then does the return keep its value as the
	# customer's credit instead of offsetting the original's open balance.
	invoice = make_simple_invoice(customer, company, amount, posting_date, paid=True, item=item)
	note = make_sales_return(invoice.name)
	# ERPNext copies dead Advances rows (no_copy references) - same clearing klik does.
	note.set("advances", [])
	note.total_advance = 0
	if posting_date:
		note.set_posting_time = 1
		note.posting_date = posting_date
	note.insert()
	note.submit()
	return note
