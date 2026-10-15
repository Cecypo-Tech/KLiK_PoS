import frappe
from frappe import _


def refuse_submitting_a_paid_mpesa_order(doc, method=None):
	"""An M-Pesa order stands for a sale its push paid, or may still: submitted as an order,
	the till treats it as gone and the payment reaches nothing (SO-00369, Allparts)."""
	if not doc.get("custom_klik_mpesa_order"):
		return
	from klik_pos.api.mpesa_order import live_push

	push = live_push(doc.name)
	if push:
		frappe.throw(
			_(
				"Order {0} is an M-Pesa checkout: request {1} paid it or may still. Reopen it from "
				"Held orders and finish the sale at the till, so the payment reaches the invoice."
			).format(doc.name, push),
			title=_("Finish the M-Pesa sale"),
		)
