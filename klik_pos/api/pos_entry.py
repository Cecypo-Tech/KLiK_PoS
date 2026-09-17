import json
import traceback

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

# Import for clearing cache and clearing draft invoices on close
from klik_pos.api.cache import clear_backend_cache
from klik_pos.api.sales_invoice import delete_draft_invoices_for_opening_entry
from klik_pos.api.sales_order import delete_held_orders_for_opening_entry
from klik_pos.klik_pos.utils import clear_pos_profile_cache, get_current_pos_profile


@frappe.whitelist()
def open_pos():
	"""Whether the caller is in an Open shift: their own, or the till shift they joined."""
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry

	return bool(get_current_pos_opening_entry())


@frappe.whitelist()
def current_shift_state():
	"""The caller's current shift (their own, or the till shift they joined), and whether
	it was opened on an earlier day. open_pos alone can't tell the caller this: it returns
	True for a stale own shift too, which is exactly the case that needs a route to
	Closing Shift instead of the checkout screen."""
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry

	from klik_pos.api.shift import is_shift_manager

	entry = get_current_pos_opening_entry()
	if not entry:
		return {"entry": None, "stale": False, "pos_profile": None, "manager": is_shift_manager()}

	row = frappe.db.get_value(
		"POS Opening Entry", entry, ["pos_profile", "period_start_date"], as_dict=True
	)
	stale = bool(row) and frappe.utils.get_date_str(row.period_start_date) != today()
	return {
		"entry": entry,
		"stale": stale,
		"pos_profile": row.pos_profile if row else None,
		"manager": is_shift_manager(),
	}


@frappe.whitelist()
def create_opening_entry():
	"""
	Create a POS Opening Entry with balance details only.
	"""
	try:
		data = frappe.local.form_dict
		if isinstance(data, str):
			data = json.loads(data)

		user = frappe.session.user

		selected_pos_profile = data.get("pos_profile")
		if selected_pos_profile:
			pos_profile = selected_pos_profile
		else:
			pos_profile = get_current_pos_profile().name if get_current_pos_profile() else None

		company = frappe.defaults.get_user_default("Company")

		if not company:
			frappe.throw(_("No default company found for user {0}").format(user))
		if not pos_profile:
			frappe.throw(_("POS Profile could not be determined"))

		balance_details = data.get("balance_details") or data.get("opening_balance", [])
		if not balance_details:
			frappe.throw(_("At least one balance detail (mode of payment) is required"))

		conflict = opening_conflict(pos_profile)
		if conflict:
			frappe.throw(_conflict_message(conflict), title=_("Shift Already Open"))

		# Create the POS Opening Entry
		doc = frappe.new_doc("POS Opening Entry")
		doc.user = user
		doc.company = company
		doc.pos_profile = pos_profile
		doc.posting_date = today()
		doc.set_posting_time = 1
		doc.period_start_date = now_datetime()

		for row in balance_details:
			detail = {
				"mode_of_payment": row.get("mode_of_payment"),
				"opening_amount": row.get("opening_amount"),
			}
			# Carried through to the row the amount sits on; validate_opening_entry decides
			# whether it was needed.
			reason = (row.get("variance_reason") or "").strip()
			if reason and frappe.db.has_column("POS Opening Entry Detail", "custom_variance_reason"):
				detail["custom_variance_reason"] = reason
			doc.append("balance_details", detail)

		doc.insert()
		doc.submit()

		# Clear POS profile cache after creating opening entry to ensure fresh data
		try:
			clear_pos_profile_cache(user=user)
			frappe.logger().info(
				f"🧹 POS Profile cache cleared after creating opening entry for user: {user}"
			)
		except Exception:
			# Do not block opening if cache clear fails; log and continue
			frappe.logger().warning(
				f"Failed to clear POS profile cache after opening entry: {frappe.get_traceback()}"
			)

		return {
			"name": doc.name,
			"message": _("POS Opening Entry created successfully."),
		}

	except frappe.ValidationError:
		# Already worded for the cashier; wrapping it again showed every message twice.
		raise
	except Exception as e:
		# Log error with full traceback in Error Log
		frappe.log_error(message=traceback.format_exc(), title="POS Opening Entry Creation Failed")
		# Throw user-friendly message
		frappe.throw(_("Failed to create POS Opening Entry: {0}").format(str(e)))


@frappe.whitelist()
def opening_conflict(pos_profile):
	"""What stands in the way of the caller opening `pos_profile`, or None.

	A cashier works in one shift, and a till runs one shift. So the caller's own Open shift
	(or the one they joined, on this till) comes first; after that, a shift someone else
	opened on this till, which the caller should join rather than duplicate. A shift opened
	before today must be closed first (ERPNext's daily shifts); for someone else's that
	means joining it and then closing it.
	"""
	from klik_pos.api.shift import _is_stale, is_shift_manager, joined_shift, open_shifts_on_till

	user = frappe.session.user
	manager = is_shift_manager(user)

	def _describe(kind, row, profile):
		return {
			"kind": kind,
			"entry": row.name,
			"pos_profile": profile,
			"period_start_date": row.period_start_date,
			"user": row.user,
			"user_name": frappe.db.get_value("User", row.user, "full_name") or row.user,
			"manager": manager,
		}

	_stale = _is_stale

	def _shifts_payload(shifts):
		return [
			{
				"entry": s.name,
				"user": s.user,
				"user_name": frappe.db.get_value("User", s.user, "full_name") or s.user,
				"period_start_date": s.period_start_date,
				"stale": _stale(s),
			}
			for s in shifts
		]

	own = frappe.get_all(
		"POS Opening Entry",
		filters={"user": user, "docstatus": 1, "status": "Open"},
		fields=["name", "user", "pos_profile", "period_start_date"],
		order_by="period_start_date desc",
	)
	if own:
		row = next((s for s in own if s.pos_profile == pos_profile), own[0])
		if row.pos_profile != pos_profile:
			return _describe("own_other_profile", row, row.pos_profile)
		return _describe("own_stale" if _stale(row) else "own_open", row, pos_profile)

	shifts = open_shifts_on_till(pos_profile)
	if not shifts:
		return None

	joined = joined_shift(user)
	if joined:
		joined_row = next((s for s in shifts if s.name == joined), None)
		if joined_row:
			return _describe("own_stale" if _stale(joined_row) else "own_open", joined_row, pos_profile)

	if len(shifts) > 1:
		oldest = shifts[0]
		kind = "till_multiple" if manager else "till_needs_manager"
		conflict = _describe(kind, oldest, pos_profile)
		conflict["open_shifts"] = _shifts_payload(shifts)
		return conflict

	shift_row = shifts[0]
	if _stale(shift_row):
		kind = "till_stale" if manager else "till_needs_manager"
		conflict = _describe(kind, shift_row, pos_profile)
		if kind == "till_needs_manager":
			conflict["open_shifts"] = _shifts_payload(shifts)
		return conflict

	return _describe("till_open", shift_row, pos_profile)


def _conflict_message(conflict):
	if conflict["kind"] == "till_needs_manager":
		if len(conflict.get("open_shifts") or []) > 1:
			return _("Till {0} has {1} open shifts. A manager must close the extra shifts first.").format(
				conflict["pos_profile"], len(conflict["open_shifts"])
			)
		return _(
			"Shift {0} on {1} was opened on {2} by {3}. A manager must close it before this till can sell."
		).format(
			conflict["entry"],
			conflict["pos_profile"],
			frappe.utils.get_date_str(conflict["period_start_date"]),
			conflict["user_name"],
		)
	if conflict["kind"] == "till_multiple":
		return _("Till {0} has {1} open shifts. Close each one before opening a new shift.").format(
			conflict["pos_profile"], len(conflict.get("open_shifts") or [])
		)
	if conflict["kind"] == "till_open":
		return _("{0} already has shift {1} open on {2}. Join it instead of opening another.").format(
			conflict["user_name"], conflict["entry"], conflict["pos_profile"]
		)
	if conflict["kind"] == "till_stale":
		return _("Shift {0} on {1} was opened on an earlier day. Join it and close it first.").format(
			conflict["entry"], conflict["pos_profile"]
		)
	if conflict["kind"] == "own_open":
		return _("Your shift {0} on {1} is already open. Continue in it instead of opening another.").format(
			conflict["entry"], conflict["pos_profile"]
		)
	if conflict["kind"] == "own_stale":
		return _("Your shift {0} on {1} was opened on an earlier day. Close it before opening a new one.").format(
			conflict["entry"], conflict["pos_profile"]
		)
	return _("Your shift {0} on {1} is still open. Close it before opening another till.").format(
		conflict["entry"], conflict["pos_profile"]
	)


def validate_opening_entry(doc, method):
	from klik_pos.api.opening_balances import enforce

	# Continuity with the last closing, and no float on a mode that never holds one.
	# On the document, so a desk-created opening is held to the same rules as the till's.
	enforce(doc)

	exists = frappe.db.exists(
		"POS Opening Entry",
		{
			"user": doc.user,
			"status": "Open",
		},
	)
	if exists:
		cashier_name = frappe.db.get_value("User", doc.user, "full_name") or doc.user
		frappe.throw(_("Cashier {0} already has an open entry: {1}").format(cashier_name, exists))


def validate_closing_entry(doc, method):
	"""Hold every POS Closing Entry to the manager rule, not only the ones create_closing_entry
	builds. On this site a cashier (Express Sales) can create and submit a POS Closing Entry
	straight from the desk, bypassing create_closing_entry's own _ensure_may_close call."""
	if frappe.flags.in_install or frappe.flags.in_patch:
		return

	row = frappe.db.get_value(
		"POS Opening Entry",
		doc.pos_opening_entry,
		["name", "user", "pos_profile", "period_start_date"],
		as_dict=True,
	)
	if not row:
		return
	_ensure_may_close(row, frappe.session.user)


@frappe.whitelist()
def create_closing_entry():
	"""
	Create a POS Closing Entry for the current user's open POS Opening Entry.
	"""
	try:
		data = _parse_request_data()
		user = frappe.session.user
		frappe.logger().info(f"POS Closing Entry Data Received: {data}")

		opening_entry = _get_open_pos_entry(user)
		_ensure_may_close(opening_entry, user)
		payment_data = _calculate_payment_reconciliation(opening_entry, data)

		doc = _create_and_submit_closing_doc(opening_entry, data, payment_data, user)

		return {
			"name": doc.name,
			"message": _("POS Closing Entry created successfully."),
		}

	except (frappe.PermissionError, frappe.ValidationError):
		# Already worded for the cashier; wrapping it again showed every message twice, and
		# a refusal is not a bug worth an Error Log.
		raise
	except Exception as e:
		frappe.log_error(message=traceback.format_exc(), title="POS Closing Entry Creation Failed")
		frappe.throw(_("Failed to create POS Closing Entry: {0}").format(str(e)))


def _parse_request_data():
	"""Parse and normalize the incoming request data."""
	data = frappe.local.form_dict
	if isinstance(data, str):
		data = json.loads(data)

	# Normalize closing_balance format
	closing_balance_raw = data.get("closing_balance", {})
	closing_balance = {}

	if isinstance(closing_balance_raw, list):
		for item in closing_balance_raw:
			if isinstance(item, dict) and "mode_of_payment" in item and "closing_amount" in item:
				closing_balance[item["mode_of_payment"]] = item["closing_amount"]
	elif isinstance(closing_balance_raw, dict):
		closing_balance = closing_balance_raw

	data["closing_balance"] = closing_balance
	return data


def _get_open_pos_entry(user):
	"""The shift the caller is closing: their own Open shift, or the till shift they joined.
	Closing it closes the till for every cashier in it."""
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry

	entry = get_current_pos_opening_entry()
	if not entry:
		frappe.throw(_("No open POS Opening Entry found for user."))
	return frappe.db.get_value(
		"POS Opening Entry",
		entry,
		["name", "pos_profile", "company", "period_start_date", "user"],
		as_dict=True,
	)


def _ensure_may_close(opening_entry, user):
	"""Refuse to close someone else's shift unless the caller is a manager, either because
	it has gone stale or because it is one of several open on the till. Their own shift, and
	any shift still on today's date on a till with exactly one open shift, stays open to
	whoever is in it - see the module docstring in shift.py for why "in it" already means
	"today or a manager"."""
	from klik_pos.api.shift import is_shift_manager, open_shifts_on_till

	if opening_entry.user == user:
		return
	if is_shift_manager(user):
		return

	stale = frappe.utils.get_date_str(opening_entry.period_start_date) != today()
	if stale:
		frappe.throw(
			_("Only a manager can close {0}, opened on {1} by {2}.").format(
				opening_entry.name,
				frappe.utils.get_date_str(opening_entry.period_start_date),
				frappe.db.get_value("User", opening_entry.user, "full_name") or opening_entry.user,
			),
			frappe.PermissionError,
		)

	shifts = open_shifts_on_till(opening_entry.pos_profile)
	if len(shifts) > 1:
		frappe.throw(
			_("Till {0} has {1} open shifts. Only a manager can close {2}.").format(
				opening_entry.pos_profile, len(shifts), opening_entry.name
			),
			frappe.PermissionError,
		)


def _calculate_payment_reconciliation(opening_entry, data):
	"""
	Calculate payment reconciliation data including opening balances,
	sales amounts, and expected vs closing amounts.
	"""
	opening_entry_name = opening_entry.name

	# Fetch opening balances
	opening_modes = frappe.get_all(
		"POS Opening Entry Detail",
		filters={"parent": opening_entry_name},
		fields=["mode_of_payment", "opening_amount"],
	)
	opening_balance_map = {row.mode_of_payment: row.opening_amount for row in opening_modes}

	# Aggregate sales by payment mode
	sales_data = frappe.db.sql(
		"""
		SELECT sip.mode_of_payment,
		       SUM(sip.amount) as total_amount,
		       COUNT(DISTINCT si.name) as transactions
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Payment` sip ON si.name = sip.parent
		WHERE si.custom_pos_opening_entry = %s
		  AND si.docstatus = 1
		GROUP BY sip.mode_of_payment
		""",
		(opening_entry_name,),
		as_dict=True,
	)
	sales_map = {row.mode_of_payment: row.total_amount for row in sales_data}

	# Money that reached the till as a Payment Entry stamped with this shift - every M-Pesa
	# receipt now - belongs in the expected amount exactly as a payment row would.
	from klik_pos.api.payment import _fetch_opening_payment_entry_data

	for row in _fetch_opening_payment_entry_data(opening_entry_name):
		sales_map[row.mode_of_payment] = flt(sales_map.get(row.mode_of_payment, 0)) + flt(row.total_amount)

	# Build reconciliation entries
	closing_balance = data.get("closing_balance", {})
	reconciliation = []

	# Process modes with closing amounts
	for mode, closing_amount in closing_balance.items():
		opening_amount = opening_balance_map.get(mode, 0)
		sales_amount = sales_map.get(mode, 0)
		expected_amount = float(opening_amount) + float(sales_amount)
		difference = float(closing_amount) - float(expected_amount)

		reconciliation.append(
			{
				"mode_of_payment": mode,
				"opening_amount": opening_amount,
				"expected_amount": expected_amount,
				"closing_amount": closing_amount,
				"difference": difference,
			}
		)

	# Process modes without closing amounts (including all opening modes if no closing data)
	for mode, opening_amount in opening_balance_map.items():
		if mode not in closing_balance:
			sales_amount = sales_map.get(mode, 0)
			expected_amount = float(opening_amount) + float(sales_amount)
			difference = 0 - float(expected_amount)

			reconciliation.append(
				{
					"mode_of_payment": mode,
					"opening_amount": opening_amount,
					"expected_amount": expected_amount,
					"closing_amount": 0,
					"difference": difference,
				}
			)

	return reconciliation


def _calculate_closing_entry_totals(opening_entry_name):
	"""
	Calculate total_quantity, net_total, and grand_total from all Sales Invoices
	linked to the opening entry. This matches standard Frappe POS behavior.
	"""
	from frappe.utils import flt

	try:
		# Aggregate all totals in a single efficient SQL query
		# One row per invoice. The join onto `Sales Invoice Item` that used to be here
		# multiplied every parent-level sum by the invoice's line count, so a shift of
		# six invoices reported 1,466.24 where the invoices totalled 1,346.76. Quantity
		# comes from the parent's own `total_qty` instead, which is what the items would
		# have summed to.
		aggregated = frappe.db.sql(
			"""
			SELECT
				COALESCE(SUM(si.net_total), 0) as net_total,
				COALESCE(SUM(si.grand_total), 0) as grand_total,
				COALESCE(SUM(si.total_qty), 0) as total_quantity
			FROM `tabSales Invoice` si
			WHERE si.custom_pos_opening_entry = %s
			  AND si.docstatus = 1
			""",
			(opening_entry_name,),
			as_dict=True,
		)

		if aggregated and len(aggregated) > 0:
			net_total = flt(aggregated[0].net_total or 0)
			grand_total = flt(aggregated[0].grand_total or 0)
			total_quantity = flt(aggregated[0].total_quantity or 0)
		else:
			net_total = grand_total = total_quantity = 0.0

		return {
			"total_quantity": total_quantity,
			"net_total": net_total,
			"grand_total": grand_total,
		}
	except Exception as e:
		frappe.logger().error(f"Error calculating closing entry totals: {frappe.get_traceback()}")
		frappe.log_error(
			message=f"Error calculating totals: {e!s}\n{traceback.format_exc()}",
			title="Closing Entry Totals Calculation Error",
		)
		# Return zeros on error to avoid blocking closing entry creation
		return {"total_quantity": 0.0, "net_total": 0.0, "grand_total": 0.0}


def _populate_sales_invoices_to_closing_entry(closing_doc, opening_entry_name):
	"""
	Populate the custom_sales_invoice child table with all Sales Invoices
	linked to the opening entry.
	"""
	try:
		# Fetch all submitted Sales Invoices linked to this opening entry
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={
				"custom_pos_opening_entry": opening_entry_name,
				"docstatus": 1,  # Only submitted invoices
			},
			fields=["name", "customer", "posting_date", "grand_total"],
			order_by="posting_date, posting_time",
		)

		# Append each invoice to the child table
		for invoice in invoices:
			closing_doc.append(
				"custom_sales_invoice",
				{
					"sales_invoice": invoice.name,
					"customer": invoice.customer,
					"posting_date": invoice.posting_date,
					"amount": invoice.grand_total,
				},
			)

		if invoices:
			frappe.logger().info(
				f"✅ Populated {len(invoices)} sales invoices to closing entry {closing_doc.name}"
			)
	except Exception as e:
		# Log error but don't block closing entry creation
		frappe.logger().error(f"Failed to populate sales invoices to closing entry: {frappe.get_traceback()}")
		frappe.log_error(
			message=f"Error populating sales invoices: {e!s}\n{traceback.format_exc()}",
			title="Sales Invoice Population Error",
		)


def _create_and_submit_closing_doc(opening_entry, data, payment_data, user):
	"""Create, populate, and submit the POS Closing Entry document."""
	doc = frappe.new_doc("POS Closing Entry")
	doc.user = user
	doc.company = opening_entry.company
	doc.pos_profile = opening_entry.pos_profile
	doc.period_start_date = opening_entry.period_start_date
	doc.period_end_date = now_datetime()
	doc.set_posting_time = 1
	doc.posting_date = today()
	doc.pos_opening_entry = opening_entry.name

	# Calculate totals from Sales Invoices linked to opening entry
	totals = _calculate_closing_entry_totals(opening_entry.name)

	# Set totals (use calculated values, fallback to frontend data if calculation fails)
	doc.total_quantity = totals.get("total_quantity") or data.get("total_quantity") or 0.0
	doc.net_total = totals.get("net_total") or data.get("net_total") or 0.0
	doc.total_amount = totals.get("grand_total") or data.get("total_amount") or 0.0
	doc.grand_total = totals.get("grand_total") or data.get("total_amount") or 0.0

	# Append payment reconciliation
	for payment in payment_data:
		doc.append("payment_reconciliation", payment)

	# Append taxes
	for tax in data.get("taxes", []):
		doc.append(
			"taxes",
			{
				"account_head": tax.get("account_head"),
				"rate": tax.get("rate"),
				"amount": tax.get("amount"),
			},
		)

	# Populate sales invoices linked to this opening entry
	_populate_sales_invoices_to_closing_entry(doc, opening_entry.name)

	# Submit and link back to opening entry
	doc.submit()
	frappe.db.set_value("POS Opening Entry", opening_entry.name, "pos_closing_entry", doc.name)

	# Every cashier who joined this shift remembered it as a user default. Left in place,
	# cancelling this Closing Entry would silently re-join them all to a shift that is
	# meant to be over. Drop the default (and its cache) for each of them now, while we
	# still know which entry just closed.
	_forget_joined_users(opening_entry.name)

	# Clear held Sales Orders and draft SIs for this session on close
	_clear_draft_invoices_on_close_if_enabled(opening_entry)
	_clear_held_orders_on_close(opening_entry)

	# Clear POS profile cache for the current user to ensure fresh data on next session
	try:
		clear_pos_profile_cache(user=user)
	except Exception:
		# Do not block closing if cache clear fails; log and continue
		frappe.logger().warning("Failed to clear POS profile cache after closing entry", exc_info=True)

	return doc


def _forget_joined_users(opening_entry_name):
	"""Release everyone who joined `opening_entry_name`, so a future cancel-and-reopen of
	its Closing Entry cannot silently re-join them."""
	from klik_pos.api.shift import JOINED_SHIFT_KEY

	joined_users = frappe.get_all(
		"DefaultValue",
		filters={"defkey": JOINED_SHIFT_KEY, "defvalue": opening_entry_name},
		pluck="parent",
	)
	for joined_user in joined_users:
		frappe.defaults.clear_default(JOINED_SHIFT_KEY, value=opening_entry_name, parent=joined_user)


def _clear_draft_invoices_on_close_if_enabled(opening_entry):
	"""If POS Profile has custom_clear_draft_invoices set, delete all draft invoices for this session."""
	try:
		pos_profile_name = opening_entry.get("pos_profile") if isinstance(opening_entry, dict) else getattr(opening_entry, "pos_profile", None)
		opening_entry_name = opening_entry.get("name") if isinstance(opening_entry, dict) else getattr(opening_entry, "name", None)
		if not pos_profile_name or not opening_entry_name:
			return
		# Check custom field (safe if field does not exist)
		clear_drafts = frappe.db.get_value("POS Profile", pos_profile_name, "custom_clear_draft_invoices")
		if clear_drafts:
			delete_draft_invoices_for_opening_entry(opening_entry_name)
	except Exception as e:
		frappe.logger().warning("Failed to clear draft invoices on close: %s", e, exc_info=True)


def _clear_held_orders_on_close(opening_entry):
	"""Always delete held Sales Orders for the session when shift is closed."""
	try:
		opening_entry_name = opening_entry.get("name") if isinstance(opening_entry, dict) else getattr(opening_entry, "name", None)
		if not opening_entry_name:
			return
		delete_held_orders_for_opening_entry(opening_entry_name)
	except Exception as e:
		frappe.logger().warning("Failed to clear held orders on close: %s", e, exc_info=True)
