"""The desk's POS Closing Entry form counts only what the payments table holds.

Since M-Pesa receipts became Payment Entries, a shift's M-Pesa money never reaches
`Sales Invoice Payment`: the zero-amount mode row is deleted at submit, so ERPNext's
`get_payments` sums nothing for it. Anyone closing a till from /app/pos-closing-entry
therefore saw the mode at 0 and a shortfall the size of the day's M-Pesa.

Klik's own closing page already merges those entries (`_calculate_payment_reconciliation`).
This puts the same number in front of the desk, by scoping Payment Entries the way that
page does - by the shift each one is stamped with - and adding them to what ERPNext
returns. The invoice, tax and change-amount arithmetic is untouched: it runs first,
inside the original, and only the payments list is added to afterwards.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.payment import _fetch_opening_payment_entry_data


@frappe.whitelist()
def get_invoices(start, end, pos_profile, user):
	"""ERPNext's `get_invoices`, with the shift's Payment Entries folded into `payments`."""
	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
		get_invoices as erpnext_get_invoices,
	)

	data = erpnext_get_invoices(start, end, pos_profile, user)
	data["payments"] = _add_shift_payment_entries(data.get("payments") or [], start, end, pos_profile, user)
	return data


def _shifts_in_period(start, end, pos_profile, user):
	"""Shifts on this till, for this cashier, whose period overlaps the one being closed.

	`period_end_date > start` rather than `>=`: a shift closed at the exact moment the
	next one opened is the previous shift, and its money was reconciled with it.
	"""
	return frappe.db.sql_list(
		"""
		SELECT name FROM `tabPOS Opening Entry`
		WHERE pos_profile = %(pos_profile)s
		  AND user = %(user)s
		  AND docstatus = 1
		  AND period_start_date <= %(end)s
		  AND (period_end_date IS NULL OR period_end_date > %(start)s)
		""",
		{"pos_profile": pos_profile, "user": user, "start": start, "end": end},
	)


def _add_shift_payment_entries(payments, start, end, pos_profile, user):
	rows = []
	for shift in _shifts_in_period(start, end, pos_profile, user):
		rows.extend(_fetch_opening_payment_entry_data(shift))
	if not rows:
		return payments

	merged = list(payments)
	by_mode = {row.get("mode_of_payment"): row for row in merged if row.get("mode_of_payment")}
	for row in rows:
		mode = row.get("mode_of_payment")
		if not mode:
			continue
		# Added to the till's own row, never in place of it: a mode can take money both
		# ways in one shift, and replacing would hide whichever came first.
		if mode in by_mode:
			by_mode[mode]["amount"] = flt(by_mode[mode].get("amount")) + flt(row.get("total_amount"))
			continue
		entry = frappe._dict({"mode_of_payment": mode, "amount": flt(row.get("total_amount"))})
		by_mode[mode] = entry
		merged.append(entry)
	return merged
