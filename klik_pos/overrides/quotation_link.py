"""A quote makes one invoice: the Sales Invoice's link to it is the truth, its status follows."""

import frappe
from frappe import _


def validate_quote_link(doc, method=None):
	quote = doc.get("custom_klik_quotation")
	if not quote:
		return
	from klik_pos.api.quotation import _quote_in_use

	# Locks the row, so two tills invoicing one quote queue up and the second sees the first.
	q = frappe.db.get_value("Quotation", quote, ["docstatus", "status"], as_dict=True, for_update=True)
	if not q or q.docstatus != 1 or q.status in ("Lost", "Cancelled"):
		frappe.throw(_("Quote {0} cannot be invoiced.").format(quote))
	other = _quote_in_use(quote)
	if other and other != doc.name:
		frappe.throw(_("Quote {0} has already been invoiced ({1}).").format(quote, other))


def on_submit_quote_link(doc, method=None):
	if doc.get("custom_klik_quotation"):
		frappe.db.set_value("Quotation", doc.custom_klik_quotation, "status", "Ordered")


def on_cancel_quote_link(doc, method=None):
	if doc.get("custom_klik_quotation"):
		frappe.db.set_value("Quotation", doc.custom_klik_quotation, "status", "Open")
