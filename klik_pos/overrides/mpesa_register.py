"""Klik's guard on `Mpesa C2B Payment Register`, a doctype owned by frappe_mpsa_payments.

Klik points a consumed register row at the Payment Entry it minted for that receipt, which
is the first time that app's own `on_cancel` has had an entry to cancel. Cancelling the row
therefore cancels an entry that is allocated to a live invoice, and ERPNext deletes that
invoice's advance rows on the way out: the sale silently reverts to unpaid, with the receipt
and the entry both gone and nothing on the invoice to say why.

So the invoice comes first. Cancel it - which releases the entry and leaves the money on the
books as the customer's credit - and only then may the receipt be cancelled.
"""

import frappe
from frappe import _


def refuse_cancel_while_invoice_live(doc, method=None):
	"""before_cancel: refuse while `doc.sales_invoice` names a submitted Sales Invoice.

	`sales_invoice` is a field klik relies on but does not own, and the whole doctype only
	exists where frappe_mpsa_payments is installed, so the absence of either is normal and
	means there is nothing to protect.
	"""
	invoice = doc.get("sales_invoice")
	if not invoice:
		return
	if frappe.db.get_value("Sales Invoice", invoice, "docstatus") != 1:
		return

	frappe.throw(
		_("Cancel Sales Invoice {0} first; this receipt is allocated to it").format(invoice),
		frappe.ValidationError,
	)
