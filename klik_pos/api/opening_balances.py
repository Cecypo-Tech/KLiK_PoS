"""What a till should open with, and what a cashier may change.

Three rules, all enforced on the document so the desk cannot bypass them either:

1. A mode's opening balance is suggested from the last closing on that POS Profile.
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


def carries_float(mode_of_payment) -> bool:
	"""True for a mode whose money physically sits in the drawer between shifts."""
	return frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == FLOAT_TYPE


def last_closing(pos_profile) -> dict:
	"""Per mode, what the last filed closing on this till counted.

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

	rows = frappe.get_all(
		"POS Closing Entry Detail",
		filters={"parent": closing.name},
		fields=["mode_of_payment", "closing_amount"],
	)
	return {
		row.mode_of_payment: {
			"amount": flt(row.closing_amount),
			"closing_entry": closing.name,
			"closed_on": closing.period_end_date,
		}
		for row in rows
		if row.mode_of_payment
	}


@frappe.whitelist()
def opening_suggestion(pos_profile):
	"""What the opening screen should show before the cashier types anything."""
	if not pos_profile:
		frappe.throw(_("A POS Profile is required to suggest opening balances."))
	frappe.has_permission("POS Profile", doc=pos_profile, throw=True)

	previous = last_closing(pos_profile)
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
		if flt(row.opening_amount) == expected:
			continue
		if (row.get(REASON_FIELD) or "").strip():
			continue

		frappe.throw(
			_(
				"{0} was counted at {1} when this till last closed, and is being opened at {2}. "
				"Say why the {3} difference is there."
			).format(
				frappe.bold(row.mode_of_payment),
				expected,
				flt(row.opening_amount),
				flt(row.opening_amount) - expected,
			),
			title=_("Opening Balance Differs From Last Closing"),
		)
