"""Z-report: the figures for one shift, or for one branch (warehouse) on one day.

One builder, rendered later as a thermal slip and an A4 page, so both show the same numbers.
The drawer ("cash_position") is counted the way klik_pos files it at shift close
(klik_pos.api.pos_entry.expected_by_mode): only money that passed through a till.
cecypo_frappe_reports' Z Report desk page imports get_z_report from here.
"""

import textwrap
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, fmt_money, get_fullname, getdate, now_datetime

NO_MODE = "(no mode)"
# An invoice's branch: its till's warehouse, else the desk invoice's set_warehouse; a return
# with neither (desk "Make Return" does not copy set_warehouse) takes its original's by the same rule.
# Every query using BRANCH_SQL aliases the invoice `si` and includes BRANCH_JOINS.
BRANCH_SQL = (
	"COALESCE(NULLIF(pp.warehouse, ''), NULLIF(si.set_warehouse, ''),"
	" NULLIF(opp.warehouse, ''), NULLIF(osi.set_warehouse, ''))"
)
BRANCH_JOINS = """LEFT JOIN `tabPOS Profile` pp ON pp.name = si.pos_profile
	LEFT JOIN `tabSales Invoice` osi ON si.is_return = 1 AND osi.name = si.return_against
	LEFT JOIN `tabPOS Profile` opp ON opp.name = osi.pos_profile"""


def _permitted_warehouses() -> set:
	"""The warehouses named by the user's User Permissions; empty means unrestricted."""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	return {p.doc for p in get_user_permissions(frappe.session.user).get("Warehouse", [])}


@frappe.whitelist()
def get_z_report(warehouse: str, date: str) -> dict:
	if not frappe.has_permission("Sales Invoice", "report"):
		frappe.throw(_("Not permitted to view sales reports."), frappe.PermissionError)
	# Warehouse read is not needed (Accounts roles lack it); User Permissions still narrow the branch.
	allowed = _permitted_warehouses()
	if allowed and warehouse not in allowed:
		frappe.throw(_("Not permitted for warehouse {0}.").format(warehouse), frappe.PermissionError)
	return build_z_report(warehouse=warehouse, date=date)


def build_z_report(
	*, opening_entry: str | None = None, warehouse: str | None = None, date: str | None = None
) -> dict:
	if opening_entry and not (warehouse or date):
		scope = _shift_scope(opening_entry)
	elif warehouse and date and not opening_entry:
		scope = _day_scope(warehouse, str(getdate(date)))
	else:
		frappe.throw(_("Pass a POS Opening Entry, or a warehouse and a date."), frappe.ValidationError)
	return _build(scope)


def _has(doctype, column):
	return frappe.db.has_column(doctype, column)


# ---- scopes ------------------------------------------------------------------------------


def _shift_scope(name):
	# Without klik's shift links on invoices and payments the shift would print as empty, not fail.
	if not (
		_has("Sales Invoice", "custom_pos_opening_entry")
		and _has("Payment Entry", "custom_pos_opening_entry")
	):
		frappe.throw(_("The shift Z-report needs klik_pos. Use the day Z-report instead."))
	opening = frappe.db.get_value(
		"POS Opening Entry",
		name,
		["name", "company", "pos_profile", "user", "period_start_date"],
		as_dict=True,
	)
	if not opening:
		frappe.throw(_("POS Opening Entry {0} not found.").format(name), frappe.DoesNotExistError)
	closing = frappe.db.get_value(
		"POS Closing Entry",
		{"pos_opening_entry": name, "docstatus": 1},
		["name", "period_end_date"],
		as_dict=True,
	)
	return {
		"scope": "shift",
		"company": opening.company,
		"pos_profile": opening.pos_profile,
		"cashier": opening.user,
		"closing": closing.name if closing else None,
		"warehouse": frappe.db.get_value("POS Profile", opening.pos_profile, "warehouse"),
		"report_no": closing.name if closing else name,
		"period_start": str(opening.period_start_date),
		"period_end": str(closing.period_end_date if closing else now_datetime()),
		"invoices": _invoices("si.custom_pos_opening_entry = %(shift)s", {"shift": name}),
		"payment_entries": _payment_entries("pe.custom_pos_opening_entry = %(shift)s", {"shift": name}),
		"expenses": _shift_expenses([name]),
		"floats": _floats([name]),
		"counted": _counted([closing.name] if closing else []),
		"excluded": 0,
		"excluded_invoices": 0,
	}


def _day_scope(warehouse, date):
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		frappe.throw(_("Warehouse {0} not found.").format(warehouse), frappe.DoesNotExistError)
	profiles = frappe.get_all("POS Profile", {"warehouse": warehouse}, pluck="name")
	shifts = profiles and frappe.get_all(
		"POS Opening Entry",
		{"docstatus": 1, "posting_date": date, "pos_profile": ("in", profiles)},
		pluck="name",
	)
	closings = profiles and frappe.get_all(
		"POS Closing Entry",
		filters=[
			["docstatus", "=", 1],
			["pos_profile", "in", profiles],
			["period_end_date", ">=", date],
			["period_end_date", "<", add_days(date, 1)],
		],
		pluck="name",
	)
	params = {"date": date, "company": company, "warehouse": warehouse}
	day = "si.posting_date = %(date)s AND si.company = %(company)s"
	invoices = _invoices(f"{day} AND {BRANCH_SQL} = %(warehouse)s", params)
	# Invoices with no branch at all (no till warehouse, no set_warehouse): counted, not lost.
	excluded_invoices = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabSales Invoice` si
		{BRANCH_JOINS}
		WHERE si.docstatus = 1 AND {day} AND {BRANCH_SQL} IS NULL""",
		params,
	)[0][0]
	entries, excluded = [], 0
	for pe in _payment_entries("pe.posting_date = %(date)s AND pe.company = %(company)s", params):
		# Branch: the shift's till, else the invoices it is allocated to, else none (left out
		# and counted). A shift-stamped entry belongs wholly to its till's branch.
		if pe.shift:
			if not pe.shift_warehouse:
				excluded += 1
			elif pe.shift_warehouse == warehouse:
				entries.append(pe)
			continue
		branched = [r for r in pe.refs if r.warehouse]
		if not branched:
			excluded += 1
		elif any(r.warehouse == warehouse for r in branched):
			# Allocations to other branches' invoices (or returns, for a refund) are theirs; the
			# unallocated remainder goes to the first allocated invoice's branch, so one branch has it.
			unallocated = flt(pe.party_amount) - sum(flt(r.allocated_amount) for r in pe.refs)
			pe.not_ours = sum(flt(r.allocated_amount) for r in pe.refs if r.warehouse != warehouse)
			if branched[0].warehouse != warehouse:
				pe.not_ours += unallocated
			entries.append(pe)
	return {
		"scope": "day",
		"company": company,
		"pos_profile": None,
		"cashier": None,
		"closing": None,
		"warehouse": warehouse,
		"report_no": f"{warehouse} {date}",
		"period_start": f"{date} 00:00:00",
		"period_end": f"{date} 23:59:59",
		"invoices": invoices,
		"payment_entries": entries,
		"expenses": _day_expenses(warehouse, date),
		"floats": _floats(shifts or []),
		"counted": _counted(closings or []),
		"excluded": excluded,
		"excluded_invoices": excluded_invoices,
	}


# ---- queries -----------------------------------------------------------------------------


def _invoices(where, params):
	shift = "si.custom_pos_opening_entry" if _has("Sales Invoice", "custom_pos_opening_entry") else "NULL"
	return frappe.db.sql(
		f"""
		SELECT si.name, si.owner, si.is_return, si.posting_date, si.posting_time, si.customer_name,
			si.base_grand_total, si.base_rounded_total, si.outstanding_amount, si.base_net_total,
			si.base_total_taxes_and_charges, si.base_discount_amount, si.base_write_off_amount,
			si.change_amount, si.base_change_amount, si.account_for_change_amount,
			NULLIF({shift}, '') AS shift,
			-- party_rate turns a party-account amount (outstanding, allocations) into company currency
			IF(IFNULL(si.party_account_currency, '') IN ('', c.default_currency), 1, si.conversion_rate)
				AS party_rate
		FROM `tabSales Invoice` si
		JOIN `tabCompany` c ON c.name = si.company
		{BRANCH_JOINS}
		WHERE si.docstatus = 1 AND {where}
		ORDER BY si.posting_date, si.posting_time, si.creation
		""",
		params,
		as_dict=True,
	)


def _payment_entries(where, params):
	"""Submitted customer receipts (Receive) and refunds (Pay), each with `refs` (its Sales
	Invoice allocations, in row order, and their branch) and, when stamped with a shift, that
	shift's till warehouse. `party_amount` is the entry in the party account's currency (that of
	its allocations); `rate` turns it into company currency."""
	if _has("Payment Entry", "custom_pos_opening_entry"):
		shift = "NULLIF(pe.custom_pos_opening_entry, '')"
		join = """LEFT JOIN `tabPOS Opening Entry` poe ON poe.name = pe.custom_pos_opening_entry
			LEFT JOIN `tabPOS Profile` spp ON spp.name = poe.pos_profile"""
		shift_wh = "spp.warehouse"
	else:
		shift, join, shift_wh = "NULL", "", "NULL"
	entries = frappe.db.sql(
		f"""
		SELECT pe.name, pe.owner, pe.payment_type, pe.mode_of_payment, pe.paid_amount,
			IF(pe.payment_type = 'Receive', pe.paid_amount, pe.received_amount) AS party_amount,
			IF(pe.payment_type = 'Receive', pe.base_paid_amount, pe.base_received_amount) AS base_amount,
			{shift} AS shift, {shift_wh} AS shift_warehouse
		FROM `tabPayment Entry` pe {join}
		WHERE pe.payment_type IN ('Receive', 'Pay') AND pe.party_type = 'Customer'
			AND pe.docstatus = 1 AND {where}
		ORDER BY pe.posting_date, pe.creation
		""",
		params,
		as_dict=True,
	)
	refs = defaultdict(list)
	if entries:
		for r in frappe.db.sql(
			f"""
			SELECT per.parent, per.reference_name, ABS(per.allocated_amount) AS allocated_amount,
				{BRANCH_SQL} AS warehouse
			FROM `tabPayment Entry Reference` per
			JOIN `tabSales Invoice` si ON si.name = per.reference_name
			{BRANCH_JOINS}
			WHERE per.reference_doctype = 'Sales Invoice' AND per.parent IN %(names)s
			ORDER BY per.parent, per.idx
			""",
			{"names": tuple(e.name for e in entries)},
			as_dict=True,
		):
			refs[r.parent].append(r)
	for e in entries:
		e.refs = refs[e.name]
		e.rate = flt(e.base_amount) / flt(e.party_amount) if flt(e.party_amount) else 1
	return entries


def _shift_expenses(shifts):
	try:
		from klik_pos.api.expense import expenses_for_shifts
	except ImportError:
		return []
	return expenses_for_shifts(shifts)


def _day_expenses(warehouse, date):
	"""klik expense Journal Entries at the branch that day, drafts included, in the shape
	klik_pos.api.expense.expenses_for_shifts returns."""
	je = "Journal Entry"
	if not all(_has(je, c) for c in ("custom_warehouse", "custom_expense_type", "custom_pos_profile")):
		return []
	out = []
	for r in frappe.get_all(
		je,
		filters={
			"custom_warehouse": warehouse,
			"posting_date": date,
			"docstatus": ("<", 2),
			"custom_expense_type": ("is", "set"),
		},
		fields=[
			"name",
			"custom_expense_type",
			"user_remark",
			"total_debit",
			"owner",
			"docstatus",
			"custom_pos_profile",
		],
		order_by="creation asc",
	):
		label, remark = r.custom_expense_type, r.user_remark or ""
		out.append(
			{
				"name": r.name,
				"label": label,
				"note": remark[len(label) + 2 :] if remark.startswith(f"{label}: ") else "",
				"amount": flt(r.total_debit, 2),
				"owner": r.owner,
				"docstatus": r.docstatus,
				"pos_profile": r.custom_pos_profile,
				"account": frappe.db.get_value(
					"Journal Entry Account",
					{"parent": r.name, "credit_in_account_currency": (">", 0)},
					"account",
				),
			}
		)
	return out


def _floats(shifts):
	floats = defaultdict(float)
	if shifts:
		for r in frappe.get_all(
			"POS Opening Entry Detail",
			{"parent": ("in", shifts)},
			["mode_of_payment", "opening_amount"],
			order_by="parent, idx",
		):
			floats[r.mode_of_payment] += flt(r.opening_amount)
	return floats


def _counted(closings):
	counted = {}
	if closings:
		for r in frappe.get_all(
			"POS Closing Entry Detail",
			{"parent": ("in", closings), "parenttype": "POS Closing Entry"},
			["mode_of_payment", "closing_amount"],
			order_by="parent, idx",
		):
			counted[r.mode_of_payment] = counted.get(r.mode_of_payment, 0) + flt(r.closing_amount)
	return counted


def _modes_by_account(pos_profile, cache):
	"""{account: mode} from the till's payment modes, first in the till's order wins.
	Same rule as klik_pos.api.pos_entry._drawer_modes_by_account."""
	if pos_profile not in cache:
		by_account = {}
		if pos_profile and frappe.db.exists("POS Profile", pos_profile):
			profile = frappe.get_cached_doc("POS Profile", pos_profile)
			order = [p.mode_of_payment for p in profile.payments]
			account_of = {
				r.parent: r.default_account
				for r in frappe.get_all(
					"Mode of Payment Account",
					{"parent": ("in", order or [""]), "company": profile.company},
					["parent", "default_account"],
				)
				if r.default_account
			}
			for mode in order:
				if account_of.get(mode):
					by_account.setdefault(account_of[mode], mode)
		cache[pos_profile] = by_account
	return cache[pos_profile]


def _change_by_invoice(invoices, rows_of):
	"""{invoice: (mode, change)}: the change left through the invoice's Cash row first, else the
	row paying into account_for_change_amount. Same rule as klik_pos.api.payment._change_given_by_mode."""
	change = {}
	for inv in invoices:
		if flt(inv.change_amount) <= 0:
			continue
		rows = [
			r for r in rows_of[inv.name] if r.type == "Cash" or r.account == inv.account_for_change_amount
		]
		rows.sort(key=lambda r: (r.type != "Cash", r.account != inv.account_for_change_amount, r.idx))
		if rows:
			change[inv.name] = (rows[0].mode_of_payment, flt(inv.change_amount))
	return change


def _printed_by(closing):
	"""Who asked for the print. QZ's agent renders a queued job as its own API user with
	ignore_print_permissions set; then it is whoever queued the newest Print Job for the closing."""
	if closing and frappe.flags.ignore_print_permissions and frappe.db.exists("DocType", "Print Job"):
		owner = frappe.db.get_value(
			"Print Job",
			{"reference_doctype": "POS Closing Entry", "reference_name": closing},
			"owner",
			order_by="creation desc",
		)
		if owner:
			return owner
	return frappe.session.user


# ---- the report --------------------------------------------------------------------------


def _money(amounts):
	return [{"mode": mode, "amount": flt(amount, 2)} for mode, amount in amounts.items()]


def _build(scope):
	"""Every figure in company currency (base_* fields), except the drawer: it keeps the
	transaction amounts klik's expected_by_mode files, so a shift's Z matches its closing."""
	invoices, entries = scope["invoices"], scope["payment_entries"]
	names = tuple(i.name for i in invoices)
	in_scope = set(names)

	rows_of = defaultdict(list)
	items_discount, taxes, advances = 0.0, [], []
	if names:
		for r in frappe.db.sql(
			"""SELECT parent, mode_of_payment, amount, base_amount, type, account, idx
			FROM `tabSales Invoice Payment`
			WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s ORDER BY parent, idx""",
			{"names": names},
			as_dict=True,
		):
			rows_of[r.parent].append(r)
		items_discount = flt(
			frappe.db.sql(
				"""SELECT SUM(sii.discount_amount * sii.qty * si.conversion_rate)
				FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
				WHERE sii.parenttype = 'Sales Invoice' AND sii.parent IN %(names)s""",
				{"names": names},
			)[0][0]
		)
		taxes = frappe.db.sql(
			"""SELECT COALESCE(NULLIF(MIN(description), ''), account_head) AS description,
				SUM(base_tax_amount_after_discount_amount) AS amount
			FROM `tabSales Taxes and Charges`
			WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s
			GROUP BY account_head ORDER BY MIN(idx), account_head""",
			{"names": names},
			as_dict=True,
		)
		advances = frappe.db.sql(
			"""SELECT parent, reference_type, reference_name, allocated_amount
			FROM `tabSales Invoice Advance`
			WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s""",
			{"names": names},
			as_dict=True,
		)
	change = _change_by_invoice(invoices, rows_of)

	# Every amount received, tagged (user, mode); the drawer separately, till money only.
	lines = []
	drawer_in, drawer_out = defaultdict(float), defaultdict(float)
	returns = {"count": 0, "modes": defaultdict(float), "total": 0.0}
	for inv in invoices:
		for r in rows_of[inv.name]:
			lines.append((inv.owner, r.mode_of_payment, flt(r.base_amount)))
			if inv.shift:
				if flt(r.amount) >= 0:
					drawer_in[r.mode_of_payment] += flt(r.amount)
				else:
					drawer_out[r.mode_of_payment] -= flt(r.amount)
			if inv.is_return:
				returns["modes"][r.mode_of_payment] += flt(r.base_amount)
		if inv.name in change:
			mode, amount = change[inv.name]
			lines.append((inv.owner, mode, -flt(inv.base_change_amount)))
			if inv.shift:
				drawer_in[mode] -= amount
		if inv.is_return:
			returns["count"] += 1
			returns["total"] += flt(inv.base_rounded_total or inv.base_grand_total)

	credit = defaultdict(float)
	refunds = defaultdict(float)  # money paid back to customers by Payment Entry, per mode
	paid_back = 0.0  # the part of those refunds settling returns already in scope
	settled = defaultdict(dict)  # {invoice: {(doctype, entry): allocated, party currency}}
	for pe in entries:
		mode = pe.mode_of_payment or NO_MODE
		ours = [r for r in pe.refs if r.reference_name in in_scope]
		allocated = sum(flt(r.allocated_amount) for r in ours)
		# not_ours: day scope's share of the entry that belongs to another branch.
		rest = flt(pe.party_amount) - allocated - flt(pe.get("not_ours"))
		if pe.payment_type == "Pay":
			# Listed under returns and off the balance, never in the drawer: klik's
			# expected_by_mode counts only Receive entries, even when stamped with the shift.
			refunds[mode] -= (allocated + rest) * pe.rate
			paid_back += allocated * pe.rate
			continue
		for r in ours:
			key = ("Payment Entry", pe.name)
			settled[r.reference_name][key] = settled[r.reference_name].get(key, 0) + flt(r.allocated_amount)
		if allocated:
			lines.append((pe.owner, mode, allocated * pe.rate))
		if flt(rest, 2):
			credit[mode] += rest * pe.rate
		if pe.shift and pe.mode_of_payment:
			drawer_in[pe.mode_of_payment] += flt(pe.paid_amount)
	# Advances settling a sale from outside scope. ERPNext also adds a Payment Entry Reference
	# row when it allocates an advance, so an entry already counted above is not counted again.
	for a in advances:
		key = (a.reference_type, a.reference_name)
		settled[a.parent].setdefault(key, flt(a.allocated_amount))

	tenders = defaultdict(float)
	users = {}
	for user, mode, amount in lines:
		tenders[mode] += amount
		users.setdefault(user, defaultdict(float))[mode] += amount

	# On credit: what each sale left unpaid when made, from the invoice itself (not its
	# outstanding_amount, which later receipts change, so a reprint still agrees).
	on_credit = defaultdict(float)
	sales = [i for i in invoices if not i.is_return]
	for inv in sales:
		paid = sum(flt(r.base_amount) for r in rows_of[inv.name]) - flt(inv.base_change_amount)
		unpaid = (
			flt(inv.base_rounded_total or inv.base_grand_total)
			- flt(inv.base_write_off_amount)
			- paid
			- sum(settled[inv.name].values()) * flt(inv.party_rate)
		)
		if flt(unpaid, 2) > 0:
			on_credit[inv.owner] += unpaid
			users.setdefault(inv.owner, defaultdict(float))

	cache, expenses = {}, []
	for e in scope["expenses"]:
		account = e.get("account")
		# An account no till mode uses (a separate petty-cash box) gets its own row.
		mode = _modes_by_account(e.get("pos_profile"), cache).get(account) or account or _("Expenses")
		drawer_out[mode] += flt(e["amount"])
		expenses.append(
			{
				"name": e["name"],
				"label": e["label"],
				"note": e["note"],
				"amount": flt(e["amount"], 2),
				"user": e["owner"],
				"user_name": get_fullname(e["owner"]),
				"pending": e["docstatus"] == 0,
			}
		)

	cash_position = []
	for mode in dict.fromkeys([*scope["floats"], *drawer_in, *drawer_out]):
		opening, got, out = scope["floats"].get(mode, 0), drawer_in.get(mode, 0), drawer_out.get(mode, 0)
		expected = flt(opening + got - out, 2)
		counted = scope["counted"].get(mode)
		cash_position.append(
			{
				"mode": mode,
				"opening": flt(opening, 2),
				"in": flt(got, 2),
				"out": flt(out, 2),
				"expected": expected,
				"counted": None if counted is None else flt(counted, 2),
				"difference": None if counted is None else flt(counted - expected, 2),
			}
		)

	# What the returns in scope came to, less what went back in the till or by Payment Entry,
	# is still owed to the customer. Refunds of earlier returns add to the total.
	on_account = returns["total"] - sum(returns["modes"].values()) + paid_back
	for mode, amount in refunds.items():
		returns["modes"][mode] += amount
	if flt(on_account, 2):
		returns["modes"][_("On account")] += on_account
	refund_total = flt(-sum(refunds.values()), 2)

	tender_total = flt(sum(tenders.values()), 2)
	credit_total = flt(sum(credit.values()), 2)
	expense_total = flt(sum(e["amount"] for e in expenses), 2)
	printed_by = _printed_by(scope["closing"])
	return {
		"scope": scope["scope"],
		"company": scope["company"],
		"tax_id": frappe.db.get_value("Company", scope["company"], "tax_id"),
		"warehouse": scope["warehouse"],
		"pos_profile": scope["pos_profile"],
		"cashier": scope["cashier"],
		"cashier_name": get_fullname(scope["cashier"]) if scope["cashier"] else None,
		"report_no": scope["report_no"],
		"printed_by": printed_by,
		"printed_by_name": get_fullname(printed_by),
		"printed_at": str(now_datetime()),
		"period_start": scope["period_start"],
		"period_end": scope["period_end"],
		"first_doc": invoices[0].name if invoices else None,
		"last_doc": invoices[-1].name if invoices else None,
		"sales_count": len(sales),
		"users": [
			{
				"user": user,
				"full_name": get_fullname(user),
				"modes": _money(modes),
				"total": flt(sum(modes.values()), 2),
				"on_credit": flt(on_credit.get(user, 0), 2),
			}
			for user, modes in users.items()
		],
		"tenders": _money(tenders),
		"tender_total": tender_total,
		# Neither is money received: shown beside the tenders, kept out of every total.
		"on_credit_total": flt(sum(on_credit.values()), 2),
		"written_off_total": flt(sum(flt(i.base_write_off_amount) for i in sales), 2),
		"credit_collected": _money(credit),
		"credit_total": credit_total,
		"returns": {
			"count": returns["count"],
			"modes": _money(returns["modes"]),
			"total": flt(sum(returns["modes"].values()), 2),
		},
		"refund_total": refund_total,
		"discount_total": flt(sum(flt(i.base_discount_amount) for i in invoices) + items_discount, 2),
		"taxes": [{"description": t.description, "amount": flt(t.amount, 2)} for t in taxes],
		"net_total": flt(sum(flt(i.base_net_total) for i in invoices), 2),
		"tax_total": flt(sum(flt(i.base_total_taxes_and_charges) for i in invoices), 2),
		"grand_total": flt(sum(flt(i.base_grand_total) for i in invoices), 2),
		"expenses": expenses,
		"expense_total": expense_total,
		"cash_position": cash_position,
		"total_balance": flt(tender_total + credit_total - expense_total - refund_total, 2),
		"outstanding": [
			{
				"name": i.name,
				"customer_name": i.customer_name,
				"grand_total": flt(i.base_grand_total, 2),
				"outstanding_amount": flt(flt(i.outstanding_amount) * flt(i.party_rate), 2),
			}
			for i in sales
			if flt(i.outstanding_amount) > 0
		],
		"excluded_payment_entries": scope["excluded"],
		"excluded_invoices": scope["excluded_invoices"],
	}


# ---- ESC/POS slip (80mm thermal, 42 columns). Double width only, never double height. ----
INIT = "\x1b@\x1c\x2e\x1b\x74\x00"
BOLD_ON, BOLD_OFF = "\x1b\x45\x01", "\x1b\x45\x00"
LEFT, CENTER = "\x1b\x61\x00", "\x1b\x61\x01"
DBLW, NORMAL = "\x1d\x21\x10", "\x1d\x21\x00"
CUT = "\x1b\x64\x04\x1d\x56\x00"


def _row(left, right, width=42):
	"""`left` and `right` on one line, right-aligned; `left` is cut so the pair always fits."""
	left, right = str(left), str(right)
	return left[: max(width - len(right) - 1, 0)].ljust(width - len(right)) + right


def z_report_escpos(opening_entry: str) -> str:
	"""The slip for a closed shift (Print Format "Z Report ESC/POS")."""
	return render_escpos(_closed_shift_report(opening_entry))


def z_report_html(opening_entry: str) -> str:
	"""The 80mm page for a closed shift (Print Format "Z Report"), previewable in the print view."""
	return render_html(_closed_shift_report(opening_entry))


def _printable(report: dict) -> dict:
	"""The report as printed: zero lines dropped, so an all-zero section has nothing left and
	the renderers skip it. Header, tender total and total balance always print."""

	def nonzero(rows):
		return [r for r in rows if flt(r["amount"], 2)]

	r = dict(report)
	r["users"] = [
		dict(u, modes=nonzero(u["modes"]))
		for u in report.get("users", [])
		if flt(u.get("total"), 2) or flt(u.get("on_credit"), 2)
	]
	r["tenders"] = nonzero(report.get("tenders", []))
	r["credit_collected"] = nonzero(report.get("credit_collected", []))
	r["taxes"] = nonzero(report.get("taxes", []))
	returns = report.get("returns") or {}
	r["returns"] = dict(returns, modes=nonzero(returns.get("modes", [])))
	r["cash_position"] = [
		c
		for c in report.get("cash_position", [])
		if any(flt(c.get(k), 2) for k in ("opening", "in", "out", "expected", "counted"))
	]
	return r


def render_html(report: dict) -> str:
	report = _printable(report)
	currency = (
		frappe.db.get_value("Company", report["company"], "default_currency")
		if report.get("company")
		else None
	)
	return frappe.render_template(
		"klik_pos/templates/z_report_80mm.html", {"report": report, "currency": currency}
	)


def _closed_shift_report(opening_entry: str) -> dict:
	"""Called from the Print Formats, which Frappe will also render for an unsaved doc dict, so the
	check is here: only a submitted closing's report, and only for a user who may print that closing
	(an open shift's expected amounts stay hidden)."""
	closing = frappe.db.get_value("POS Closing Entry", {"pos_opening_entry": opening_entry, "docstatus": 1})
	# QZ renders queued jobs as its print agent's API user with ignore_print_permissions set; the
	# cashier's own print permission was checked when the job was queued (QZ's reprint).
	if not closing or (
		not frappe.flags.ignore_print_permissions
		and not frappe.has_permission("POS Closing Entry", "print", doc=closing)
	):
		frappe.throw(_("Not permitted to print this Z-report."), frappe.PermissionError)
	return build_z_report(opening_entry=opening_entry)


def render_escpos(report: dict, width: int | None = None) -> str:
	"""The slip as a str of latin-1 code points (one char per printer byte)."""
	report = _printable(report)
	if width is None:
		try:
			from cecypo_qz_extension.escpos import qz_columns

			width = qz_columns(42)
		except ImportError:
			width = 42
	company = report.get("company")
	currency = frappe.db.get_value("Company", company, "default_currency") if company else None
	hr = "-" * width
	out = [INIT]

	def money(amount):
		return fmt_money(amount, currency=currency)

	def line(text=""):
		out.append(f"{text}\n")

	def head(title):
		line(f"{BOLD_ON}{title}{BOLD_OFF}")

	def pairs(rows, key="amount"):
		for r in rows:
			line(_row(r["mode"], money(r[key]), width))

	out.append(CENTER)
	for part in textwrap.wrap(company or "", width // 2) or [""]:
		line(f"{DBLW}{part}{NORMAL}")
	for part in textwrap.wrap(report.get("warehouse") or "", width):
		line(part)
	line(f"{BOLD_ON}{_('Z REPORT')}{BOLD_OFF}")
	out.append(LEFT)
	line(hr)
	if report.get("tax_id"):
		line(_row(_("Tax ID"), report["tax_id"], width))
	line(_row(_("Report"), report.get("report_no") or "", width))
	if report.get("pos_profile"):
		line(_row(_("Till"), report["pos_profile"], width))
	if report.get("cashier"):
		line(_row(_("Cashier"), report.get("cashier_name") or report["cashier"], width))
	opened, closed = (_("Opened"), _("Closed")) if report.get("pos_profile") else (_("From"), _("To"))
	line(_row(opened, str(report.get("period_start") or "")[:16], width))
	line(_row(closed, str(report.get("period_end") or "")[:16], width))
	if report.get("printed_by"):
		line(_row(_("Printed by"), report.get("printed_by_name") or report["printed_by"], width))
	line(_row(_("Printed on"), str(report.get("printed_at") or "")[:16], width))
	if report.get("first_doc"):
		line(_row(_("First invoice"), report["first_doc"], width))
		line(_row(_("Last invoice"), report["last_doc"], width))
	line(_row(_("Sales"), report.get("sales_count", 0), width))
	line(hr)

	on_credit = _("On credit (not in totals)")
	if report["users"]:
		head(_("Sales by user"))
		for u in report["users"]:
			line(_row(u["full_name"] or u["user"], money(u["total"]), width))
			for m in u["modes"]:
				line(_row(f"  {m['mode']}", money(m["amount"]), width))
			if u.get("on_credit"):
				line(_row(f"  {on_credit}", money(u["on_credit"]), width))
		line(hr)

	head(_("Tender types"))
	pairs(report.get("tenders", []))
	line(f"{BOLD_ON}{_row(_('Total'), money(report.get('tender_total', 0)), width)}{BOLD_OFF}")
	if report.get("on_credit_total"):
		line(_row(on_credit, money(report["on_credit_total"]), width))
	if report.get("written_off_total"):
		line(_row(_("Written off"), money(report["written_off_total"]), width))
	line(hr)

	if report["credit_collected"]:
		head(_("Credit collected / deposits"))
		pairs(report["credit_collected"])
		line(_row(_("Total"), money(report.get("credit_total", 0)), width))
		line(hr)

	returns = report["returns"]
	if returns.get("count") or returns["modes"]:
		head(_("Returns"))
		line(_row(_("Count"), returns.get("count", 0), width))
		pairs(returns["modes"])
		line(_row(_("Total"), money(returns.get("total", 0)), width))
		line(hr)

	if flt(report.get("discount_total"), 2):
		head(_("Discounts"))
		line(_row(_("Discounts (net of returns)"), money(report["discount_total"]), width))
		line(hr)

	if flt(report.get("grand_total"), 2) or flt(report.get("tax_total"), 2):
		head(_("Tax"))
		line(_row(_("Taxable total"), money(report.get("net_total", 0)), width))
		for t in report["taxes"]:
			line(_row(f"  {t['description']}", money(t["amount"]), width))
		if flt(report.get("tax_total"), 2):
			line(_row(_("Tax total"), money(report["tax_total"]), width))
		line(_row(_("Grand total"), money(report.get("grand_total", 0)), width))
		line(hr)

	if report.get("expenses"):
		head(_("Expenses"))
		for e in report["expenses"]:
			line(_row(e["label"] or e["name"], money(e["amount"]), width))
			who = ": ".join(x for x in (e.get("user_name") or e.get("user"), e.get("note")) if x)
			for part in textwrap.wrap(who, width, initial_indent="  ", subsequent_indent="  "):
				line(part)
			if e.get("pending"):
				line(f"  ({_('awaiting approval')})")
		line(_row(_("Total"), money(report.get("expense_total", 0)), width))
		line(hr)

	if report["cash_position"]:
		head(_("Cash position"))
		for c in report["cash_position"]:
			line(c["mode"][:width])
			for label, key in (("Opening", "opening"), ("In", "in"), ("Out", "out")):
				if flt(c[key], 2):
					line(_row(f"  {_(label)}", money(c[key]), width))
			line(_row(f"  {_('Expected')}", money(c["expected"]), width))
			if c["counted"] is not None:
				line(_row(f"  {_('Counted')}", money(c["counted"]), width))
				if flt(c["difference"], 2):
					line(_row(f"  {_('Diff')}", money(c["difference"]), width))
		line(hr)

	line(f"{BOLD_ON}{_row(_('Total balance'), money(report.get('total_balance', 0)), width)}{BOLD_OFF}")
	if report.get("excluded_invoices") or report.get("excluded_payment_entries"):
		text = _("Not counted: {0} invoices, {1} payments (no branch)").format(
			report.get("excluded_invoices", 0), report.get("excluded_payment_entries", 0)
		)
		for part in textwrap.wrap(text, width):
			line(part)
	out.append(CUT)
	return "".join(out)
