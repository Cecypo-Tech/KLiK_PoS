"""What a till should open with, and what a cashier may change.

Three rules, all enforced on the document so the desk cannot bypass them either:

1. A mode's opening balance is suggested from the last closing on that POS Profile, less
   any cash handed over for banking at that closing: the float left in the drawer.
   ERPNext carries nothing forward, so before this the field opened at zero every day and
   whatever the cashier typed became the figure the shift was judged against.
2. Changing a suggested figure needs a reason, stored on the row beside the amount it
   explains. Understating an opening float is the one edit that hides a shortfall: the
   count at close still reconciles, and the missing money is never asked about.
3. Only a cash mode carries a float at all. Card, bank transfer and M-Pesa money never
   sits in the drawer, and the balance of the account it lands in is not a cashier's
   business, so those modes open at zero.
"""

import frappe
from frappe import _
from frappe.utils import flt

FLOAT_TYPE = "Cash"
REASON_FIELD = "custom_variance_reason"
PREVIOUS_FIELD = "custom_previous_closing_amount"
BANKED_FIELD = "custom_banked_amount"


def carries_float(mode_of_payment) -> bool:
	"""True for a mode whose money physically sits in the drawer between shifts."""
	return frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == FLOAT_TYPE


def last_closing(pos_profile) -> dict:
	"""Per mode, what the last filed closing on this till left in the drawer: the count, less
	what was handed over for banking.

	Keyed on the POS Profile rather than the cashier: the drawer stays with the till when
	the shift changes hands.
	"""
	closing = frappe.db.get_value(
		"POS Closing Entry",
		{"pos_profile": pos_profile, "docstatus": 1},
		["name", "period_end_date"],
		order_by="period_end_date desc, creation desc",
		as_dict=True,
	)
	if not closing:
		return {}

	fields = ["mode_of_payment", "closing_amount"]
	# A site that has not migrated has no banked column; it leaves nothing out, as before.
	if frappe.db.has_column("POS Closing Entry Detail", BANKED_FIELD):
		fields.append(BANKED_FIELD)
	rows = frappe.get_all("POS Closing Entry Detail", filters={"parent": closing.name}, fields=fields)
	# Rounded to the field's precision: 1234.56 - 1000 is 234.55999999999995 in float, and
	# the opening's exact comparison would then ask about a difference of 0.00.
	precision = frappe.get_precision("POS Closing Entry Detail", "closing_amount")
	result = {}
	for row in rows:
		if not row.mode_of_payment:
			continue
		counted = flt(row.closing_amount)
		banked = flt(row.get(BANKED_FIELD))
		result[row.mode_of_payment] = {
			"amount": flt(counted - banked, precision),
			"counted": counted,
			"banked": banked,
			"closing_entry": closing.name,
			"closed_on": closing.period_end_date,
		}
	return result


@frappe.whitelist()
def opening_suggestion(pos_profile):
	"""What the opening screen should show before the cashier types anything."""
	if not pos_profile:
		frappe.throw(_("A POS Profile is required to suggest opening balances."))
	frappe.has_permission("POS Profile", doc=pos_profile, throw=True)

	from klik_pos.api.shift import may_close_on_till

	previous = last_closing(pos_profile)
	# On a till whose users do not close it, what the manager counted and banked at the last
	# close stays with the manager; the float carried into this shift is still shown.
	show_last_count = may_close_on_till(pos_profile)
	modes = frappe.get_all(
		"POS Payment Method",
		filters={"parent": pos_profile, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "`default`"],
		order_by="idx asc",
	)
	# The till's default mode leads, then profile order. `default` cannot be sorted on in
	# the query: frappe rejects a backticked column in order_by.
	modes.sort(key=lambda m: 0 if m.get("default") else 1)

	suggestions = []
	for mode in modes:
		if not mode.mode_of_payment:
			continue
		mode_type = frappe.db.get_value("Mode of Payment", mode.mode_of_payment, "type") or "General"
		float_mode = mode_type == FLOAT_TYPE
		last = previous.get(mode.mode_of_payment) or {}
		suggestions.append(
			{
				"mode_of_payment": mode.mode_of_payment,
				"type": mode_type,
				"carries_float": float_mode,
				# A mode that holds no float opens at zero whatever it closed at.
				"suggested_amount": flt(last.get("amount")) if float_mode else 0.0,
				"previous_closing_amount": flt(last.get("amount")) if float_mode else 0.0,
				"previous_closing_entry": last.get("closing_entry") if float_mode else None,
				"previous_closed_on": last.get("closed_on") if float_mode else None,
				"previous_counted_amount": flt(last.get("counted")) if float_mode and show_last_count else 0.0,
				"previous_banked_amount": flt(last.get("banked")) if float_mode and show_last_count else 0.0,
			}
		)
	return {"pos_profile": pos_profile, "modes": suggestions}


def enforce(doc):
	"""validate: apply the three rules to a POS Opening Entry, whoever created it."""
	if not doc.get("balance_details"):
		return

	previous = last_closing(doc.pos_profile) if doc.pos_profile else {}
	has_reason_field = frappe.db.has_column("POS Opening Entry Detail", REASON_FIELD)
	has_previous_field = frappe.db.has_column("POS Opening Entry Detail", PREVIOUS_FIELD)
	precision = frappe.get_precision("POS Opening Entry Detail", "opening_amount")

	for row in doc.balance_details:
		if not row.mode_of_payment:
			continue

		if not carries_float(row.mode_of_payment):
			if flt(row.opening_amount):
				frappe.throw(
					_(
						"{0} holds no float: its money goes straight to its account, so it opens at 0, not {1}."
					).format(frappe.bold(row.mode_of_payment), flt(row.opening_amount)),
					title=_("Opening Balance Not Allowed"),
				)
			if has_reason_field:
				row.set(REASON_FIELD, None)
			if has_previous_field:
				row.set(PREVIOUS_FIELD, 0)
			continue

		expected = flt((previous.get(row.mode_of_payment) or {}).get("amount"))
		if has_previous_field:
			row.set(PREVIOUS_FIELD, expected)

		# Nothing to reconcile against on a till that has never been closed.
		if not previous.get(row.mode_of_payment):
			continue
		# Nowhere to record an explanation means nowhere to demand one: a site that has
		# not migrated yet must still be able to open its tills.
		if not has_reason_field:
			continue
		if flt(row.opening_amount, precision) == flt(expected, precision):
			continue
		if (row.get(REASON_FIELD) or "").strip():
			continue

		frappe.throw(
			_(
				"{0} was left at {1} when this till last closed, and is being opened at {2}. "
				"Say why the {3} difference is there."
			).format(
				frappe.bold(row.mode_of_payment),
				expected,
				flt(row.opening_amount),
				flt(row.opening_amount) - expected,
			),
			title=_("Opening Balance Differs From Last Closing"),
		)


def enforce_banking(doc):
	"""validate: a POS Closing Entry can only hand over cash it counted, from a mode that
	keeps cash in the drawer. Whoever files it - the till or the desk."""
	for row in doc.get("payment_reconciliation") or []:
		banked = flt(row.get(BANKED_FIELD))
		if not banked or not row.mode_of_payment:
			continue
		if banked < 0:
			frappe.throw(
				_("{0}: the amount handed over for banking cannot be negative.").format(
					frappe.bold(row.mode_of_payment)
				),
				title=_("Banking Not Allowed"),
			)
		if not carries_float(row.mode_of_payment):
			frappe.throw(
				_("{0} holds no cash in the drawer, so none of it can be handed over for banking.").format(
					frappe.bold(row.mode_of_payment)
				),
				title=_("Banking Not Allowed"),
			)
		if banked > flt(row.closing_amount):
			frappe.throw(
				_("{0}: {1} is to be handed over for banking, but only {2} was counted.").format(
					frappe.bold(row.mode_of_payment), banked, flt(row.closing_amount)
				),
				title=_("Banking Not Allowed"),
			)
