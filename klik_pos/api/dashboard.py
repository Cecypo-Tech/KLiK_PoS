"""One server-side answer for the Sales Dashboard.

The old dashboard fetched the 100 most recently modified invoices and summed them in the
browser, so a till past its hundredth sale of the period showed an arbitrary total rather
than a slightly wrong one. Worse, the money never balanced: unpaid (deni) invoices carry
no `Sales Invoice Payment` rows, so credit sales sat in headline revenue and were absent
from the payment breakdown, and the two figures were sourced differently by construction
- revenue from `grand_total` (billed), percentages from payment rows (collected).

This module answers the whole page from one call, in company currency, over any range and
any set of the caller's tills, and holds itself to an identity the reader can check:

    billed == collected_at_sale + collected_later + deni - refunds_owed + write_off

The residual is returned as `identity.unexplained` instead of being hidden. Every term
comes from the same set of invoices, so a nonzero residual is a data bug worth chasing,
never a timing artefact.

Scope is invoice-based, exactly like the POS Closing Entry: money is attributed to the
range of the invoice it settles, not to the day the cash arrived. A Payment Entry received
today against last week's credit sale belongs to last week.

Permissions are enforced here explicitly (role, then company, then each profile) rather
than through `apply_sql_permissions`: the match conditions that helper adds would silently
empty the page for a user with a User Permission on some unrelated doctype, which is the
failure mode this dashboard exists to remove.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, flt, get_first_day, getdate, nowdate

from klik_pos.api.sales_invoice import _can_view_sales_dashboard

VALID_RANGES = ("shift", "today", "week", "month", "custom")
MAX_CUSTOM_RANGE_DAYS = 92

# The threshold api/customer.py already uses to call a balance settled, restated here so
# a rounding remainder of a cent is not reported as an unpaid credit sale.
RECEIVABLE_EPSILON = 0.001

# A held order older than this is a forgotten one. Two hours is a v1 guess; make it a POS
# Settings field the moment a second customer disagrees with it.
HELD_ORDER_STALE_HOURS = 2

# What the customer actually owes, and therefore what the payment rows settle and what
# `outstanding_amount` is computed against. Summing `grand_total` instead leaves the
# identity short by the rounding on every invoice - on dev's three open shifts that was
# exactly 1.24 across three invoices, small enough to look like a mystery and large enough
# to make the page's one balancing line untrue.
PAYABLE_TOTAL = """CASE
	WHEN si.disable_rounded_total = 0 AND si.base_rounded_total != 0 THEN si.base_rounded_total
	ELSE si.base_grand_total
END"""

REGISTER_DOCTYPE = "Mpesa C2B Payment Register"
REGISTER_URL_DOCTYPE = "Mpesa C2B Payment Register URL"

# Where an exception row lands when the reader taps it. The SPA reads these as routes, so
# they are named here once rather than rebuilt in the components.
INVOICE_HISTORY_ROUTE = "/invoice"
# The register has no page in the SPA; it is read in the Desk, so this link deliberately
# leaves the app. Anything under /app is opened as a full navigation by the client.
MPESA_REGISTER_ROUTE = "/app/mpesa-c2b-payment-register"


@frappe.whitelist()
def get_dashboard_summary(
	company: str | None = None,
	pos_profiles=None,
	date_range: str = "shift",
	date_from: str | None = None,
	date_to: str | None = None,
	**kwargs,
) -> dict:
	"""Everything the Sales Dashboard shows, for one company and a set of its tills.

	`range` is the name the HTTP caller uses; it is accepted as an alias so the query
	string reads naturally without shadowing the builtin inside this module.
	"""
	date_range = (kwargs.get("range") or date_range or "shift").strip()

	company = _resolve_company(company)
	available = _available_profiles(company)
	profiles = _resolve_profiles(company, pos_profiles, available)
	scope = _resolve_scope(company, profiles, date_range, date_from, date_to)
	# The picker needs to know which tills exist, not only which were asked for; without it
	# the client cannot offer the choice without a second round trip.
	scope["available_profiles"] = available

	if not profiles:
		# A company with no POS profile the caller may read is not an error; it is an
		# empty page. Returning zeros keeps the client free of a second empty-state path.
		return _empty_response(company, scope)

	condition, params = _scope_sql(scope)

	billed = _billed(condition, params)
	at_sale, change_amount = _collected_at_sale(condition, params)
	later = _collected_later(condition, params)
	mpesa = _unmatched_mpesa(company)

	mode_rows = _build_mode_rows(at_sale, later, change_amount, mpesa["by_shortcode"])
	collected_at_sale = sum(flt(row["amount"]) for row in mode_rows)
	collected_later = sum(flt(row["later"]) for row in mode_rows)

	identity = {
		"billed": flt(billed["billed"], 2),
		"billed_gross": flt(billed["billed_gross"], 2),
		"collected": flt(collected_at_sale + collected_later, 2),
		"collected_at_sale": flt(collected_at_sale, 2),
		"collected_later": flt(collected_later, 2),
		"deni": flt(billed["deni"], 2),
		"deni_invoices": int(billed["credit_invoices"]),
		"deni_customers": int(billed["credit_customers"]),
		"refunds_owed": flt(billed["refunds_owed"], 2),
		"write_off": flt(billed["write_off"], 2),
		"invoices": int(billed["invoices"]),
		"returns": int(billed["returns"]),
		"returns_total": flt(billed["returns_total"], 2),
		"currency": _company_currency(company),
	}
	identity["unexplained"] = flt(
		identity["billed"]
		- identity["collected_at_sale"]
		- identity["collected_later"]
		- identity["deni"]
		+ identity["refunds_owed"]
		- identity["write_off"],
		2,
	)

	return {
		"scope": scope,
		"identity": identity,
		"collected_by_mode": mode_rows,
		"exceptions": _exceptions(company, scope, mpesa["unmapped"]),
		"performance": _performance(condition, params, billed),
	}


# --------------------------------------------------------------------------------------
# Scope and permission
# --------------------------------------------------------------------------------------


def _resolve_company(company: str | None) -> str:
	"""The company whose money this call may read.

	Checked in the order the reader would ask it: may you open this page at all, then may
	you open it for *this* company. A System Manager or Administrator may name any company;
	everyone else is held to their own default, which is what the SPA sends anyway.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _can_view_sales_dashboard(roles):
		raise frappe.PermissionError(_("Not permitted to view the Sales Dashboard"))

	default_company = frappe.defaults.get_user_default("Company")
	company = (company or default_company or "").strip()
	if not company:
		raise frappe.ValidationError(_("No company given and no default company is set"))

	unrestricted = bool({"Administrator", "System Manager"} & set(roles))
	if not unrestricted and company != default_company:
		raise frappe.PermissionError(_("Not permitted to view {0}").format(company))

	if not frappe.db.exists("Company", company):
		raise frappe.ValidationError(_("Company {0} does not exist").format(company))

	return company


def _available_profiles(company: str) -> list[str]:
	"""Every enabled till of the company, in name order."""
	return [
		row.name
		for row in frappe.get_all(
			"POS Profile", filters={"company": company, "disabled": 0}, fields=["name"], order_by="name"
		)
	]


def _resolve_profiles(company: str, pos_profiles, available: list[str]) -> list[str]:
	"""The tills to report on: those asked for, or every enabled one of the company.

	A profile belonging to another company is refused rather than quietly dropped - a
	silently narrowed scope is how a dashboard comes to show a number nobody can explain.
	"""
	if isinstance(pos_profiles, str):
		pos_profiles = frappe.parse_json(pos_profiles) if pos_profiles.strip() else None
	if isinstance(pos_profiles, str):  # a bare "Till 1" rather than a JSON list
		pos_profiles = [pos_profiles]

	if not pos_profiles:
		return available

	requested = [str(p).strip() for p in pos_profiles if str(p).strip()]
	allowed = set(available)
	for profile in requested:
		if profile not in allowed:
			raise frappe.ValidationError(
				_("POS Profile {0} does not belong to {1}").format(profile, company)
			)
	return sorted(set(requested))


def _resolve_scope(company, profiles, date_range, date_from, date_to) -> dict:
	"""Turn the requested range into the dates or the open shifts to sum over."""
	if date_range not in VALID_RANGES:
		raise frappe.ValidationError(
			_("Unknown range {0}. Expected one of: {1}").format(date_range, ", ".join(VALID_RANGES))
		)

	scope = {
		"company": company,
		"pos_profiles": profiles,
		"range": date_range,
		"date_from": None,
		"date_to": None,
		"opening_entries": [],
		"open_shifts": [],
		"fallback": None,
	}

	if date_range == "shift":
		open_shifts = (
			frappe.get_all(
				"POS Opening Entry",
				filters={"pos_profile": ["in", profiles], "status": "Open", "docstatus": 1},
				fields=["name", "pos_profile", "period_start_date"],
				order_by="period_start_date asc",
			)
			if profiles
			else []
		)
		if open_shifts:
			scope["open_shifts"] = [
				{
					"name": s.name,
					"pos_profile": s.pos_profile,
					"period_start_date": str(s.period_start_date) if s.period_start_date else None,
				}
				for s in open_shifts
			]
			scope["opening_entries"] = [s.name for s in open_shifts]
			return scope

		# Nothing is open. Today's figures are the useful answer, but the reader must be
		# told they are looking at a different question than the one they asked.
		scope["fallback"] = "today"
		date_range = "today"

	today = getdate(nowdate())
	if date_range == "today":
		scope["date_from"] = scope["date_to"] = str(today)
	elif date_range == "week":
		scope["date_from"] = str(add_days(today, -today.weekday()))
		scope["date_to"] = str(today)
	elif date_range == "month":
		scope["date_from"] = str(get_first_day(today))
		scope["date_to"] = str(today)
	else:
		if not date_from or not date_to:
			raise frappe.ValidationError(_("A custom range needs both date_from and date_to"))
		start, end = getdate(date_from), getdate(date_to)
		if end < start:
			raise frappe.ValidationError(_("date_to falls before date_from"))
		if (end - start).days + 1 > MAX_CUSTOM_RANGE_DAYS:
			raise frappe.ValidationError(
				_("A custom range may cover at most {0} days").format(MAX_CUSTOM_RANGE_DAYS)
			)
		scope["date_from"], scope["date_to"] = str(start), str(end)

	return scope


def _scope_sql(scope) -> tuple[str, dict]:
	"""The WHERE fragment every aggregation shares, plus its parameters.

	Every query in this module joins back to `tabSales Invoice si`, so one fragment keeps
	them provably summing over the same rows - which is what makes the identity meaningful.
	"""
	params = {
		"company": scope["company"],
		"profiles": tuple(scope["pos_profiles"]) or ("",),
		"eps": RECEIVABLE_EPSILON,
	}
	condition = "si.company = %(company)s AND si.docstatus = 1 AND si.pos_profile IN %(profiles)s"

	if scope["opening_entries"]:
		params["opening_entries"] = tuple(scope["opening_entries"])
		condition += " AND si.custom_pos_opening_entry IN %(opening_entries)s"
	else:
		params["date_from"] = scope["date_from"]
		params["date_to"] = scope["date_to"]
		condition += " AND si.posting_date BETWEEN %(date_from)s AND %(date_to)s"

	return condition, params


def _company_currency(company: str) -> str:
	return frappe.db.get_value("Company", company, "default_currency") or ""


def _empty_response(company, scope) -> dict:
	return {
		"scope": scope,
		"identity": {
			"billed": 0.0,
			"billed_gross": 0.0,
			"collected": 0.0,
			"collected_at_sale": 0.0,
			"collected_later": 0.0,
			"deni": 0.0,
			"deni_invoices": 0,
			"deni_customers": 0,
			"refunds_owed": 0.0,
			"write_off": 0.0,
			"unexplained": 0.0,
			"invoices": 0,
			"returns": 0,
			"returns_total": 0.0,
			"currency": _company_currency(company),
		},
		"collected_by_mode": [],
		"exceptions": [],
		"performance": {
			"kpis": {"revenue": 0.0, "invoices": 0, "average": 0.0, "items": 0.0},
			"hourly": [],
			"top_items": [],
			"cashiers": [],
			"recent": [],
		},
	}


# --------------------------------------------------------------------------------------
# Aggregations
# --------------------------------------------------------------------------------------


def _billed(condition: str, params: dict) -> dict:
	"""Billed, and everything else the invoice header alone can answer.

	`outstanding_amount` is the only money field here that is not stored in company
	currency, so it is converted with the invoice's own rate; a zero rate on stray data
	would otherwise erase a debt rather than report it.
	"""
	payable = PAYABLE_TOTAL
	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM({payable}), 0) AS billed,
			COALESCE(SUM(si.base_grand_total), 0) AS billed_gross,
			COALESCE(SUM(si.base_net_total), 0) AS net,
			COALESCE(SUM(si.total_qty), 0) AS qty,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN 0 ELSE 1 END), 0) AS invoices,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN 1 ELSE 0 END), 0) AS returns,
			COALESCE(SUM(CASE WHEN si.is_return = 1 THEN {payable} ELSE 0 END), 0)
				AS returns_total,
			COALESCE(SUM(si.base_change_amount), 0) AS change_amount,
			COALESCE(SUM(si.base_write_off_amount), 0) AS write_off,
			COALESCE(SUM(CASE WHEN si.outstanding_amount > %(eps)s
				THEN si.outstanding_amount * COALESCE(NULLIF(si.conversion_rate, 0), 1)
				ELSE 0 END), 0) AS deni,
			COALESCE(SUM(CASE WHEN si.is_return = 1 AND si.outstanding_amount < -%(eps)s
				THEN -si.outstanding_amount * COALESCE(NULLIF(si.conversion_rate, 0), 1)
				ELSE 0 END), 0) AS refunds_owed,
			COALESCE(SUM(CASE WHEN si.outstanding_amount > %(eps)s THEN 1 ELSE 0 END), 0)
				AS credit_invoices,
			COUNT(DISTINCT CASE WHEN si.outstanding_amount > %(eps)s THEN si.customer END)
				AS credit_customers
		FROM `tabSales Invoice` si
		WHERE {condition}
		""",
		params,
		as_dict=True,
	)
	return row[0] if row else frappe._dict()


def _collected_at_sale(condition: str, params: dict) -> tuple[list, float]:
	"""What the till took at the moment of sale, by mode, and the change it gave back.

	Change is a parent-level field, so it cannot be summed in the same query as the payment
	rows without being multiplied by the number of modes on the invoice. It is fetched
	separately and taken off the cash row by the caller.
	"""
	rows = frappe.db.sql(
		f"""
		SELECT
			sip.mode_of_payment AS mode,
			COALESCE(SUM(sip.base_amount), 0) AS amount,
			COUNT(DISTINCT sip.parent) AS count
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE {condition} AND sip.mode_of_payment IS NOT NULL AND sip.mode_of_payment != ''
		GROUP BY sip.mode_of_payment
		""",
		params,
		as_dict=True,
	)
	change = frappe.db.sql(
		f"SELECT COALESCE(SUM(si.base_change_amount), 0) FROM `tabSales Invoice` si WHERE {condition}",
		params,
	)
	return rows, flt(change[0][0] if change else 0)


def _collected_later(condition: str, params: dict) -> list:
	"""Deni settled afterwards, by the mode it was settled in.

	Only the amount allocated to an in-scope invoice counts: one Payment Entry can settle
	several invoices, and counting its `paid_amount` would credit this shift with money
	that paid last month's debt. A `Pay` entry against a return is a refund going out, not
	collection coming in, so only `Receive` is summed.
	"""
	return frappe.db.sql(
		f"""
		SELECT
			pe.mode_of_payment AS mode,
			COALESCE(SUM(per.allocated_amount * COALESCE(NULLIF(pe.source_exchange_rate, 0), 1)), 0)
				AS amount,
			COUNT(DISTINCT per.reference_name) AS count
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name
		WHERE {condition}
			AND per.reference_doctype = 'Sales Invoice'
			AND per.docstatus = 1
			AND pe.docstatus = 1
			AND pe.payment_type = 'Receive'
			AND pe.mode_of_payment IS NOT NULL AND pe.mode_of_payment != ''
		GROUP BY pe.mode_of_payment
		""",
		params,
		as_dict=True,
	)


def _build_mode_rows(at_sale, later, change_amount, unmatched_by_shortcode) -> list:
	"""One row per mode of payment, at-sale and later kept apart.

	They stay apart because a mode's row must still be checkable against what the till's
	Closing Entry shows for that mode; folding in money that arrived days later would make
	the two disagree for a good reason, which is indistinguishable from disagreeing for a
	bad one.
	"""
	rows: dict[str, dict] = {}
	for row in at_sale:
		rows.setdefault(row["mode"], {"mode": row["mode"], "amount": 0.0, "later": 0.0, "count": 0})
		rows[row["mode"]]["amount"] += flt(row["amount"])
		rows[row["mode"]]["count"] += int(row["count"] or 0)
	for row in later:
		rows.setdefault(row["mode"], {"mode": row["mode"], "amount": 0.0, "later": 0.0, "count": 0})
		rows[row["mode"]]["later"] += flt(row["amount"])

	# Change only ever leaves the drawer as cash, so it comes off the cash row. If the
	# profile's cash mode is named something else and no row matched, it is still deducted
	# from the largest at-sale row rather than vanishing from the identity.
	if change_amount:
		cash_row = next((r for r in rows.values() if r["mode"].strip().lower() == "cash"), None)
		if cash_row is None and rows:
			cash_row = max(rows.values(), key=lambda r: r["amount"])
		if cash_row is not None:
			cash_row["amount"] -= flt(change_amount)

	for shortcode, unmatched in unmatched_by_shortcode.items():
		mode = unmatched.get("mode_of_payment")
		if not mode:
			continue
		rows.setdefault(mode, {"mode": mode, "amount": 0.0, "later": 0.0, "count": 0})
		rows[mode]["shortcode"] = shortcode
		rows[mode]["unmatched"] = int(unmatched["count"])
		rows[mode]["unmatched_amount"] = flt(unmatched["amount"], 2)

	ordered = sorted(
		rows.values(), key=lambda r: (r["amount"] + r["later"], r.get("unmatched", 0)), reverse=True
	)
	for row in ordered:
		row["amount"] = flt(row["amount"], 2)
		row["later"] = flt(row["later"], 2)
	return ordered


def _unmatched_mpesa(company: str) -> dict:
	"""M-Pesa money that arrived and has not been attached to a sale.

	The register lives in frappe_mpsa_payments and the fields that map a shortcode to a
	Mode of Payment exist on some sites only as hand-made Custom Fields, so both the
	doctypes and those two fields are checked before they are read. Where the mapping is
	missing the shortcode is still reported - as an unmapped exception rather than against
	a mode row - because unattached money is exactly what the reader must not lose sight of.
	"""
	empty = {"by_shortcode": {}, "unmapped": []}
	if not frappe.db.exists("DocType", REGISTER_DOCTYPE):
		return empty

	from klik_pos.api.mpesa import _mpesa_shortcodes_for_company

	shortcodes = _mpesa_shortcodes_for_company(company)
	if not shortcodes:
		return empty

	rows = frappe.db.sql(
		"""
		SELECT businessshortcode AS shortcode, COUNT(*) AS count,
			COALESCE(SUM(transamount), 0) AS amount
		FROM `tabMpesa C2B Payment Register`
		WHERE docstatus = 0 AND businessshortcode IN %(shortcodes)s
		GROUP BY businessshortcode
		""",
		{"shortcodes": tuple(shortcodes)},
		as_dict=True,
	)
	if not rows:
		return empty

	mapping = _shortcode_to_mode(company)
	by_shortcode, unmapped = {}, []
	for row in rows:
		shortcode = str(row["shortcode"])
		mode = mapping.get(shortcode)
		by_shortcode[shortcode] = {
			"count": int(row["count"]),
			"amount": flt(row["amount"]),
			"mode_of_payment": mode,
		}
		if not mode:
			unmapped.append(
				{"shortcode": shortcode, "count": int(row["count"]), "amount": flt(row["amount"])}
			)
	return {"by_shortcode": by_shortcode, "unmapped": unmapped}


def _shortcode_to_mode(company: str) -> dict:
	"""Shortcode -> Mode of Payment, or an empty mapping where the site cannot express it."""
	if not frappe.db.exists("DocType", REGISTER_URL_DOCTYPE):
		return {}

	meta = frappe.get_meta(REGISTER_URL_DOCTYPE)
	fieldnames = {df.fieldname for df in meta.fields}
	if not {"company", "mode_of_payment"}.issubset(fieldnames):
		return {}

	rows = frappe.get_all(
		REGISTER_URL_DOCTYPE,
		filters={"company": company, "register_status": "Success"},
		fields=["business_shortcode", "mode_of_payment"],
	)
	return {
		str(row.business_shortcode): row.mode_of_payment
		for row in rows
		if row.business_shortcode and row.mode_of_payment
	}


def _exceptions(company: str, scope: dict, unmapped_mpesa: list) -> list:
	"""Only what is actually wrong, each row carrying where to go and see it.

	Counts are deliberately not date-scoped: a submission that failed on Friday is still
	unresolved on Monday, and a dashboard that hides it once the range moves on is how it
	stays unresolved.
	"""
	profiles = scope["pos_profiles"]
	rows = []

	failed = frappe.db.count(
		"Sales Invoice",
		{"docstatus": 0, "queue_status": "Failed", "pos_profile": ["in", profiles], "company": company},
	)
	if failed:
		rows.append(
			{
				"key": "failed_submissions",
				"count": failed,
				"link": {"route": INVOICE_HISTORY_ROUTE, "params": {"tab": "queue_failed"}},
			}
		)

	queued = frappe.db.count(
		"Sales Invoice",
		{
			"docstatus": 0,
			"queue_status": ["in", ["Queued", "Processing"]],
			"pos_profile": ["in", profiles],
			"company": company,
		},
	)
	if queued:
		rows.append(
			{
				"key": "queued_submissions",
				"count": queued,
				"link": {"route": INVOICE_HISTORY_ROUTE, "params": {"tab": "queued"}},
			}
		)

	held = frappe.db.count(
		"Sales Order",
		{
			"docstatus": 0,
			"custom_is_klik_held": 1,
			"company": company,
			"modified": ["<", add_to_date(None, hours=-HELD_ORDER_STALE_HOURS)],
		},
	)
	if held:
		rows.append(
			{
				"key": "stale_held_orders",
				"count": held,
				"link": {"route": INVOICE_HISTORY_ROUTE, "params": {"tab": "draft"}},
			}
		)

	stale_shifts = frappe.db.count(
		"POS Opening Entry",
		{
			"status": "Open",
			"docstatus": 1,
			"pos_profile": ["in", profiles],
			"period_start_date": ["<", nowdate()],
		},
	)
	if stale_shifts:
		rows.append({"key": "shifts_open_past_today", "count": stale_shifts, "link": None})

	if unmapped_mpesa:
		rows.append(
			{
				"key": "unmatched_mpesa_unmapped",
				"count": sum(row["count"] for row in unmapped_mpesa),
				"amount": flt(sum(row["amount"] for row in unmapped_mpesa), 2),
				"shortcodes": [row["shortcode"] for row in unmapped_mpesa],
				"link": {"route": MPESA_REGISTER_ROUTE, "params": {"docstatus": "0"}},
			}
		)

	return rows


def _performance(condition: str, params: dict, billed: dict) -> dict:
	"""The second tier: what sold, when, and who rang it."""
	invoices = int(billed.get("invoices") or 0)
	revenue = flt(billed.get("billed") or 0, 2)

	hourly = frappe.db.sql(
		f"""
		SELECT HOUR(si.posting_time) AS hour,
			COALESCE(SUM({PAYABLE_TOTAL}), 0) AS amount,
			COUNT(*) AS count
		FROM `tabSales Invoice` si
		WHERE {condition}
		GROUP BY HOUR(si.posting_time)
		ORDER BY hour
		""",
		params,
		as_dict=True,
	)

	top_items = frappe.db.sql(
		f"""
		SELECT sii.item_code, sii.item_name,
			COALESCE(SUM(sii.base_amount), 0) AS amount,
			COALESCE(SUM(sii.qty), 0) AS qty
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {condition}
		GROUP BY sii.item_code, sii.item_name
		ORDER BY amount DESC
		LIMIT 5
		""",
		params,
		as_dict=True,
	)

	cashiers = frappe.db.sql(
		f"""
		SELECT si.owner AS cashier,
			COALESCE(SUM({PAYABLE_TOTAL}), 0) AS amount,
			COUNT(*) AS count
		FROM `tabSales Invoice` si
		WHERE {condition}
		GROUP BY si.owner
		ORDER BY amount DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)

	recent = frappe.db.sql(
		f"""
		SELECT si.name, si.customer_name, {PAYABLE_TOTAL} AS amount, si.is_return,
			si.posting_date, si.posting_time, si.status
		FROM `tabSales Invoice` si
		WHERE {condition}
		ORDER BY si.posting_date DESC, si.posting_time DESC
		LIMIT 5
		""",
		params,
		as_dict=True,
	)
	_attach_payment_modes(recent)

	return {
		"kpis": {
			"revenue": revenue,
			"invoices": invoices,
			"average": flt(revenue / invoices, 2) if invoices else 0.0,
			"items": flt(billed.get("qty") or 0, 2),
		},
		"hourly": [
			{"hour": int(row["hour"] or 0), "amount": flt(row["amount"], 2), "count": int(row["count"])}
			for row in hourly
		],
		"top_items": [
			{
				"item_code": row["item_code"],
				"item_name": row["item_name"],
				"amount": flt(row["amount"], 2),
				"qty": flt(row["qty"], 2),
			}
			for row in top_items
		],
		"cashiers": [
			{"cashier": row["cashier"], "amount": flt(row["amount"], 2), "count": int(row["count"])}
			for row in cashiers
		],
		"recent": [
			{
				"name": row["name"],
				"customer_name": row["customer_name"],
				"amount": flt(row["amount"], 2),
				"is_return": bool(row["is_return"]),
				"time": str(row["posting_time"] or ""),
				"status": row["status"],
				"mode_of_payment": row.get("mode_of_payment") or "-",
			}
			for row in recent
		],
	}


def _attach_payment_modes(invoices: list) -> None:
	"""The same de-duplicated mode string Invoice History shows.

	Three M-Pesa rows on one invoice read as one 'Mpesa-111222', not as the same name
	repeated three times - which is what broke strict-equality filtering elsewhere.
	"""
	if not invoices:
		return
	rows = frappe.db.sql(
		"""
		SELECT parent, mode_of_payment
		FROM `tabSales Invoice Payment`
		WHERE parent IN %(names)s AND mode_of_payment IS NOT NULL AND mode_of_payment != ''
		ORDER BY idx
		""",
		{"names": tuple(inv["name"] for inv in invoices)},
		as_dict=True,
	)
	by_invoice: dict[str, list] = {}
	for row in rows:
		by_invoice.setdefault(row["parent"], []).append(row["mode_of_payment"])
	for invoice in invoices:
		modes = list(dict.fromkeys(by_invoice.get(invoice["name"], [])))
		invoice["mode_of_payment"] = "/".join(modes) if modes else "-"
