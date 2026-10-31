"""Petty-cash expenses recorded at the till, each a Journal Entry stamped with till, warehouse and shift."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from klik_pos.api.sales_invoice import get_current_pos_opening_entry
from klik_pos.api.shift import is_shift_manager


def may_record_expenses(pos_profile, user=None):
	"""The till has a 'Pay expenses from' account, and the user is ticked on it or is a shift manager."""
	if not pos_profile or not frappe.db.get_value("POS Profile", pos_profile, "custom_expense_account"):
		return False
	user = user or frappe.session.user
	ticked = frappe.db.get_value(
		"POS Profile User", {"parent": pos_profile, "user": user}, "custom_can_record_expenses"
	)
	return bool(ticked) or is_shift_manager(user)


def _shift_profile():
	"""(opening entry, its POS Profile) for the caller's current shift, else (None, None)."""
	entry = get_current_pos_opening_entry()
	return entry, entry and frappe.db.get_value("POS Opening Entry", entry, "pos_profile")


@frappe.whitelist()
def expense_types():
	_, profile = _shift_profile()
	if not may_record_expenses(profile):
		return []
	return [
		{"label": label}
		for label in frappe.get_all(
			"POS Profile Expense Type",
			{"parent": profile, "parenttype": "POS Profile"},
			pluck="label",
			order_by="idx asc",
		)
	]


@frappe.whitelist(methods=["POST"])
def record_expense(label, amount, note=""):
	entry, profile_name = _shift_profile()
	if not entry:
		frappe.throw(_("No open shift. Open a shift before recording an expense."))
	if not may_record_expenses(profile_name):
		frappe.throw(_("You may not record expenses on this till."), frappe.PermissionError)

	try:
		amount = flt(amount, 2) if str(amount).strip() and float(amount) else 0
	except (TypeError, ValueError):
		amount = 0
	if amount <= 0:
		frappe.throw(_("The amount must be a number above zero."))

	profile = frappe.get_doc("POS Profile", profile_name)
	account = next((r.expense_account for r in profile.custom_expense_types if r.label == label), None)
	if not account:
		frappe.throw(_("{0} is not an expense type on this till.").format(label))

	# Re-check on the server what the form's link filters only suggest.
	row = frappe.db.get_value("Account", account, ["is_group", "root_type", "company"], as_dict=True)
	if not row or row.is_group or row.root_type != "Expense" or row.company != profile.company:
		frappe.throw(
			_("The expense account for {0} must be a ledger Expense account of {1}.").format(
				label, profile.company
			)
		)
	pay = frappe.db.get_value(
		"Account",
		profile.custom_expense_account,
		["is_group", "account_type", "company"],
		as_dict=True,
	)
	if not pay or pay.is_group or pay.company != profile.company or pay.account_type not in ("Cash", "Bank"):
		frappe.throw(
			_("'Pay expenses from' must be a Cash or Bank ledger account of {0}.").format(profile.company)
		)

	note = (note or "").strip()
	cost_center = profile.cost_center or frappe.get_cached_value("Company", profile.company, "cost_center")
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Cash Entry",
			"company": profile.company,
			"posting_date": nowdate(),
			"user_remark": f"{label}: {note}" if note else label,
			"custom_pos_profile": profile.name,
			"custom_warehouse": profile.warehouse,
			"custom_pos_opening_entry": entry,
			"custom_expense_type": label,
			"accounts": [
				{"account": account, "debit_in_account_currency": amount, "cost_center": cost_center},
				{
					"account": profile.custom_expense_account,
					"credit_in_account_currency": amount,
					"cost_center": cost_center,
				},
			],
		}
	)
	je.insert(ignore_permissions=True)
	if not profile.custom_expenses_need_approval:
		je.submit()
	return {"name": je.name, "docstatus": je.docstatus, "amount": amount, "label": label}


_ROW_FIELDS = ["name", "custom_expense_type", "user_remark", "total_debit", "owner", "docstatus", "creation"]


def _rows(filters):
	rows = frappe.get_all(
		"Journal Entry",
		filters={**filters, "docstatus": ("<", 2)},
		fields=[*_ROW_FIELDS, "custom_pos_profile", "custom_warehouse"],
		order_by="creation asc",
	)
	out = []
	for r in rows:
		label = r.custom_expense_type or ""
		remark = r.user_remark or ""
		note = remark[len(label) + 2 :] if remark.startswith(f"{label}: ") else ""
		out.append(
			{
				"name": r.name,
				"label": label,
				"note": note,
				"amount": flt(r.total_debit, 2),
				"owner": r.owner,
				"docstatus": r.docstatus,
				"creation": r.creation,
				"pos_profile": r.custom_pos_profile,
				"warehouse": r.custom_warehouse,
			}
		)
	return out


@frappe.whitelist()
def shift_expenses(opening_entry=None):
	"""Expenses of the caller's current shift, or of `opening_entry` (managers only)."""
	entry, profile = _shift_profile()
	if opening_entry and opening_entry != entry:
		if not is_shift_manager():
			frappe.throw(_("Only a manager may view another shift's expenses."), frappe.PermissionError)
		entry = opening_entry
	elif not may_record_expenses(profile):
		return []
	if not entry:
		return []
	return [
		{k: v for k, v in r.items() if k not in ("pos_profile", "warehouse")}
		for r in _rows({"custom_pos_opening_entry": entry})
	]


def expenses_for_shifts(opening_entries):
	"""Same rows plus pos_profile, warehouse and `account` (the credit account), for Task 3 / the Z-report."""
	if not opening_entries:
		return []
	rows = _rows({"custom_pos_opening_entry": ("in", list(opening_entries))})
	for r in rows:
		r["account"] = frappe.db.get_value(
			"Journal Entry Account", {"parent": r["name"], "credit_in_account_currency": (">", 0)}, "account"
		)
	return rows
