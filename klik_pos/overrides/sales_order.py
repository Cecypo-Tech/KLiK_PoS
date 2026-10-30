import frappe
from frappe import _


def refuse_submitting_a_paid_mpesa_order(doc, method=None):
	"""An M-Pesa order stands for a sale its push paid, or may still: submitted as an order,
	the till treats it as gone and the payment reaches nothing (SO-00369, Allparts)."""
	if not doc.get("custom_klik_mpesa_order"):
		return
	from klik_pos.api.mpesa import _klik_entry_for_transid
	from klik_pos.api.mpesa_order import EXPRESS, REGISTER, _pushes, live_push

	# The two cases the till hands to the desk (_paid_push_refusal): a sale paid twice, and a
	# push whose receipt is already booked (SO-00368). Refusing them here too left no way out.
	paid = _pushes(doc.name, ("Completed",))
	if len(paid) > 1:
		return
	transid = paid and frappe.db.get_value(EXPRESS, paid[0], "transaction_id")
	if transid and (
		frappe.db.exists(REGISTER, {"transid": transid, "payment_entry": ["is", "set"]})
		or _klik_entry_for_transid(transid)
	):
		return

	push = live_push(doc.name)
	if push:
		frappe.throw(
			_(
				"Order {0} is an M-Pesa checkout: request {1} paid it or may still. Reopen it from "
				"Held orders and finish the sale at the till, so the payment reaches the invoice."
			).format(doc.name, push),
			title=_("Finish the M-Pesa sale"),
		)


def _held_print_blocked(doc):
	"""A held draft whose till has Block Printing Held Orders on."""
	if doc.docstatus != 0 or not doc.get("custom_is_klik_held") or not doc.get("custom_pos_profile"):
		return False
	return bool(frappe.db.get_value("POS Profile", doc.custom_pos_profile, "custom_block_held_order_print"))


def held_order_print_permission(doc=None, ptype=None, user=None, debug=False):
	"""Sales Order has_permission: no `print` on a blocked held order. Print view and PDF
	check it, and so does the QZ button, which shows disabled. Deny-only hook: True
	everywhere else."""
	if ptype != "print" or doc is None or isinstance(doc, str):
		return True
	return not _held_print_blocked(doc)


def refuse_printing_a_held_order(doc, method=None, *args, **kwargs):
	"""Sales Order before_print: the same block for renders that skip the permission check
	(QZ renders its queued jobs with ignore_print_permissions)."""
	if _held_print_blocked(doc):
		frappe.throw(
			_("Held order {0} can't be printed: till {1} blocks printing held orders.").format(
				doc.name, doc.custom_pos_profile
			),
			frappe.PermissionError,
		)
