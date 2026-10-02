"""The draft Sales Order an M-Pesa STK push is sent from, until the cashier submits the sale.

The payment dialog used to make a draft Sales Invoice before every push and keep it for good
once a push went out, so every push the customer never paid left a POS-numbered invoice draft
behind. A push now names a draft Sales Order (`custom_klik_mpesa_order`). Submitting the sale
turns it into the invoice the way a held order checks out: klik's own submit builds the invoice
from the cart, the invoice records the order (`powerpack_source_order`), every push sent from
the order is pointed at the invoice, and the order is deleted.

While the dialog is open the order is not a hold (`custom_is_klik_held` 0). If the cashier
leaves with a push that may still pay, or already has, the order is kept and becomes a held
order, so it can be finished from the Held tab; otherwise it is deleted.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from klik_pos.api import sales_order
from klik_pos.api.sales_invoice import (
	_check_discardable_links,
	_keeping_naming_series,
	_parse_extra_fields,
	create_draft_invoice,
	parse_invoice_data,
	submit_draft_invoice,
)

EXPRESS = "Mpesa Express Request"
# A push in either state may pay the order, or has: the order must not be lost.
LIVE_PUSH_STATUSES = ("In Progress", "Completed")
SAVEPOINT = "klik_submit_mpesa_order"


def _pushes(order_name, statuses=None):
	"""Pushes sent from the order, newest first."""
	if not frappe.db.exists("DocType", EXPRESS):
		return []
	filters = {"reference_doctype": "Sales Order", "reference_name": order_name}
	if statuses:
		filters["status"] = ["in", list(statuses)]
	return frappe.get_all(EXPRESS, filters=filters, pluck="name", order_by="creation desc")


def live_push(order_name):
	"""A push sent from the order that may still pay it, or already did; else None."""
	pushes = _pushes(order_name, LIVE_PUSH_STATUSES)
	return pushes[0] if pushes else None


def last_push(order_name):
	"""What checkout needs to pick up the order's newest push, or None."""
	pushes = _pushes(order_name)
	if not pushes:
		return None
	return frappe.db.get_value(
		EXPRESS,
		pushes[0],
		[
			"name",
			"status",
			"amount",
			"phone_number",
			"transaction_id",
			"checkout_request_id",
			"payment_gateway",
			"result_desc",
		],
		as_dict=True,
	)


def delete_order(so):
	"""Delete a draft order nothing live depends on.

	A Failed push still names the order, and Frappe refuses to delete a document a submitted
	one links to; it paid nothing, so it does not stand in the way. Any other link still does.
	"""
	_check_discardable_links(so)
	with _keeping_naming_series():
		frappe.delete_doc("Sales Order", so.name, ignore_permissions=True, force=True)


def _load(order_id):
	"""Lock the M-Pesa order and check the caller may act on it."""
	sales_order._lock_held_order(order_id)
	so = frappe.get_doc("Sales Order", order_id)
	if not so.get("custom_klik_mpesa_order"):
		frappe.throw(_("Order {0} is not an M-Pesa checkout order.").format(order_id))
	if not sales_order._may_act_on_held_order(so):
		frappe.throw(_("You are not allowed to act on order {0}.").format(order_id))
	return so


@frappe.whitelist(methods=["POST"])
def save_mpesa_order(data):
	"""Create the order a push is sent from, or bring an existing one up to the cart.

	Called before every push, so the order - and the amount the push asks for - always matches
	what the cashier is charging for.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		from klik_pos.api.pos_profile import validate_required_extra_fields

		validate_required_extra_fields(_parse_extra_fields(data))
		(
			customer,
			items,
			_amount_paid,
			sales_and_tax_charges,
			_mode_of_payment,
			business_type,
			roundoff_amount,
			delivery_charge,
			delivery_personnel,
			_is_credit_sale,
			_allow_partial_payment,
			_due_date,
			salesperson,
			tax_id,
			_enable_background_submission,
			_loyalty_redemption,
		) = parse_invoice_data(data)

		cart_meta = sales_order._build_cart_meta(
			data,
			items,
			business_type,
			salesperson,
			tax_id,
			delivery_charge,
			delivery_personnel,
			sales_and_tax_charges,
			roundoff_amount,
		)
		order_discount_amount = flt(data.get("orderDiscountAmount") or 0)

		order_id = data.get("mpesa_order_id")
		if order_id:
			so = _load(order_id)
			if so.docstatus != 0:
				frappe.throw(_("Order {0} is no longer a draft.").format(order_id))
			sales_order._rebuild_sales_order(
				so, customer, items, sales_and_tax_charges, cart_meta, order_discount_amount
			)
			so.custom_klik_cart_meta = json.dumps(cart_meta)
		else:
			so = sales_order._build_sales_order_doc(
				customer, items, sales_and_tax_charges, cart_meta, order_discount_amount
			)

		# In checkout, not a hold: off the Held tab until the dialog lets go of it.
		so.custom_is_klik_held = 0
		so.custom_klik_mpesa_order = 1
		if so.is_new():
			so.insert(ignore_permissions=True)
		else:
			so.save(ignore_permissions=True)

		# Sales Order.tax_id is fetched from the Customer on every save; keep the buyer's PIN.
		if tax_id and so.meta.has_field("tax_id") and so.tax_id != tax_id:
			so.db_set("tax_id", tax_id)

		return {
			"success": True,
			"order_name": so.name,
			"grand_total": flt(so.rounded_total or so.grand_total),
		}
	except Exception as e:
		# Before logging, as create_held_order does: insert() takes the order's number before
		# validating, and a swallowed failure would let the request commit that burnt number.
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Save M-Pesa Order Error")
		return {"success": False, "message": str(e)}


def _create_invoice_draft(order_id, data):
	"""The invoice draft submit_draft_invoice finishes; it rebuilds it from the cart anyway."""
	result = create_draft_invoice(
		{
			**(data or {}),
			# Same as the draft M-Pesa used to make up front: it is paid by the submit, so the
			# cash-sale "positive payment" check does not apply to the draft.
			"status": "held",
			"enable_background_invoice_submission": False,
		}
	)
	if not result.get("success"):
		frappe.throw(
			result.get("message") or _("Could not create the invoice for order {0}.").format(order_id)
		)
	return result["invoice_name"]


def _invoice_already_made(order_id):
	"""The response for a submit that already went through, or None.

	The order is gone once its invoice exists, and its pushes then name that invoice. A
	retried submit (the reply was lost on the way back) must answer with it, not ring the
	sale up a second time.
	"""
	if frappe.db.exists("Sales Order", order_id) or not frappe.db.exists("DocType", EXPRESS):
		return None
	invoice = frappe.db.get_value(
		EXPRESS,
		{"account_reference": order_id, "reference_doctype": "Sales Invoice"},
		"reference_name",
	)
	if not invoice or not frappe.db.exists("Sales Invoice", invoice):
		return None
	invoice_doc = frappe.get_doc("Sales Invoice", invoice)
	if invoice_doc.docstatus == 2:
		return None
	return {
		"success": True,
		"replayed": True,
		"message": _("Order {0} was already submitted as {1}.").format(order_id, invoice),
		"invoice_name": invoice,
		"queue_status": invoice_doc.get("queue_status"),
		"invoice": invoice_doc,
	}


def _hand_over_to_invoice(order_id, invoice):
	"""The order is now the invoice: its pushes follow, the invoice records it, it goes."""
	for name in _pushes(order_id):
		frappe.db.set_value(
			EXPRESS,
			name,
			{"reference_doctype": "Sales Invoice", "reference_name": invoice},
			update_modified=False,
		)
	if frappe.get_meta("Sales Invoice").has_field("powerpack_source_order") and not frappe.db.get_value(
		"Sales Invoice", invoice, "powerpack_source_order"
	):
		frappe.db.set_value(
			"Sales Invoice", invoice, "powerpack_source_order", order_id, update_modified=False
		)
	with _keeping_naming_series():
		frappe.delete_doc("Sales Order", order_id, ignore_permissions=True, force=True)


@frappe.whitelist(methods=["POST"])
def submit_mpesa_order(order_id, data=None, held_order_id=None, remarks=None):
	"""Turn the M-Pesa order into the submitted (or queued) Sales Invoice.

	All of it - the invoice, the push links, the order's deletion - happens or none of it does.
	held_order_id: the held order the cart came from, when it is not this order itself.
	"""
	if isinstance(data, str):
		data = json.loads(data)

	replay = _invoice_already_made(order_id)
	if replay:
		return replay

	frappe.db.savepoint(SAVEPOINT)
	try:
		try:
			so = _load(order_id)
		except frappe.DoesNotExistError:
			# Another request finished it while this one waited for the lock.
			return _invoice_already_made(order_id) or sales_order._gone_response(
				order_id,
				_("M-Pesa order {0} no longer exists - it was finished or cleared elsewhere.").format(
					order_id
				),
			)
		if so.docstatus != 0:
			return sales_order._gone_response(order_id, sales_order._held_order_gone(order_id))

		waiting = _pushes(order_id, ("In Progress",))
		if waiting:
			# Its payment would land on a sale already finished with other money.
			return {
				"success": False,
				"code": "mpesa_request_waiting",
				"order_id": order_id,
				"error": _("M-Pesa request {0} for this sale is still waiting on the customer.").format(
					waiting[0]
				),
			}

		draft = _create_invoice_draft(order_id, data)
		other_held_order = held_order_id if held_order_id and held_order_id != order_id else None
		result = submit_draft_invoice(draft, data, other_held_order, remarks)
		if not result.get("success"):
			frappe.db.rollback(save_point=SAVEPOINT)
			return result

		_hand_over_to_invoice(order_id, result.get("invoice_name") or draft)
		return result
	except Exception as e:
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.log_error(frappe.get_traceback(), f"Submit M-Pesa Order Error: {order_id}")
		return {"success": False, "error": str(e)}


@frappe.whitelist(methods=["POST"])
def discard_mpesa_order(order_id):
	"""The cashier left checkout without finishing the M-Pesa sale.

	The order is deleted unless a push sent from it may still pay it, or already has; then it
	is kept as a held order so the sale can be finished from the Held tab.
	"""
	state = frappe.db.get_value(
		"Sales Order",
		order_id,
		["docstatus", "owner", "custom_klik_mpesa_order"],
		as_dict=True,
		for_update=True,
	)
	if not state:
		return {"success": True, "kept": False, "message": _("Order {0} is already gone.").format(order_id)}
	if state.docstatus != 0 or not state.custom_klik_mpesa_order or state.owner != frappe.session.user:
		return {
			"success": False,
			"error": _("Order {0} was kept: it is not this checkout's to discard.").format(order_id),
		}

	live = live_push(order_id)
	if live:
		frappe.db.set_value(
			"Sales Order",
			order_id,
			{
				"custom_is_klik_held": 1,
				"custom_pos_opening_entry": sales_order.get_current_pos_opening_entry() or "",
			},
		)
		return {
			"success": True,
			"kept": True,
			"order_name": order_id,
			"message": _(
				"Order {0} was kept: M-Pesa request {1} was sent from it, and its payment needs this "
				"order. Finish it from Held orders before charging this customer again."
			).format(order_id, live),
		}

	delete_order(frappe.get_doc("Sales Order", order_id))
	return {"success": True, "kept": False, "message": _("Order {0} discarded.").format(order_id)}
