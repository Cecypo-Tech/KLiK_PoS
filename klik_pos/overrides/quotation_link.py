"""A quote makes one invoice: the Sales Invoice's link to it is the truth, its status follows."""

import frappe
from frappe import _


def validate_quote_link(doc, method=None):
	quote = doc.get("custom_klik_quotation")
	if not quote:
		return
	# Locks the row, so two tills invoicing one quote queue up and the second sees the first.
	q = frappe.db.get_value("Quotation", quote, ["docstatus", "status"], as_dict=True, for_update=True)
	if not q or q.docstatus != 1 or q.status in ("Lost", "Cancelled"):
		frappe.throw(_("Quote {0} cannot be invoiced.").format(quote))
	# Locking read (sees the latest committed row, not our snapshot) of any OTHER live invoice.
	other = frappe.db.get_value(
		"Sales Invoice",
		{"custom_klik_quotation": quote, "docstatus": ["<", 2], "name": ["!=", doc.name or ""]},
		"name",
		for_update=True,
	)
	if other:
		frappe.throw(_("Quote {0} has already been invoiced ({1}).").format(quote, other))


def on_submit_quote_link(doc, method=None):
	if doc.get("custom_klik_quotation"):
		frappe.db.set_value("Quotation", doc.custom_klik_quotation, "status", "Ordered")


def on_cancel_quote_link(doc, method=None):
	# Only undo our own "Ordered"; a quote marked Lost in desk stays Lost.
	quote = doc.get("custom_klik_quotation")
	if quote and frappe.db.get_value("Quotation", quote, "status") == "Ordered":
		frappe.db.set_value("Quotation", quote, "status", "Open")
