from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils import cint

_cached_company_data = {}


def _till_cache():
	"""The till each f"{user}|{shift or 'none'}" resolves to - for this request only.

	It was process-wide: each web worker kept its own, so a deletion handled by one worker
	left the others resolving the reused shift name to the deleted till.
	"""
	if not hasattr(frappe.local, "klik_till_cache"):
		frappe.local.klik_till_cache = {}
	return frappe.local.klik_till_cache


# The till's picked warehouse, sent with every request (klik_spa/src/utils/warehouseHeader.ts).
WAREHOUSE_HEADER = "X-Klik-Warehouse"


def checked_warehouse(profile, wanted):
	"""`wanted` if this till may sell from it, None for the till's own; throws otherwise."""
	wanted = (wanted or "").strip()
	if not wanted or wanted == profile.get("warehouse"):
		return None
	if not cint(profile.get("allow_warehouse_change")):
		frappe.throw(_("Till {0} does not allow switching warehouse.").format(profile.get("name")))
	from klik_pos.api.pos_profile import leaf_warehouses_for

	if wanted not in leaf_warehouses_for(profile.get("company"), frappe.session.user):
		frappe.throw(_("You cannot sell from warehouse {0} at this till.").format(wanted))
	return wanted


def requested_warehouse(profile):
	"""The warehouse the till picked for this request, checked; None for the till's own."""
	request = getattr(frappe.local, "request", None)
	headers = getattr(request, "headers", None)
	# URL-encoded by the till: a header value is Latin-1 only.
	return checked_warehouse(profile, unquote(headers.get(WAREHOUSE_HEADER) or "") if headers else None)


def _resolve_pos_profile_name():
	"""Resolve the active POS Profile name for the current user/opening entry.

	Uses identity-only caching keyed by user and opening entry (the name is
	stable for a session; only the profile's field values may change).
	"""
	user = frappe.session.user

	from klik_pos.api.sales_invoice import get_current_pos_opening_entry

	current_opening_entry = get_current_pos_opening_entry()
	cache_key = f"{user}|{current_opening_entry or 'none'}"

	cache = _till_cache()
	if cache_key in cache:
		return cache[cache_key]

	if current_opening_entry:
		pos_profile_name = frappe.db.get_value("POS Opening Entry", current_opening_entry, "pos_profile")
	else:
		pos_profile_name = frappe.get_value("POS Profile User", {"user": user}, "parent")
		if not pos_profile_name:
			frappe.throw(_("No POS Profile found for user {0}").format(user))

	# Cache identity (name) only
	cache[cache_key] = pos_profile_name
	# A rolled-back shift's name is handed out again; its till must not answer for the next one.
	frappe.db.after_rollback.add(lambda: cache.pop(cache_key, None))
	return pos_profile_name


def get_current_pos_profile():
	"""Get the active POS Profile with identity-only caching keyed by user and opening entry.

	Returns a fresh POS Profile Doc each call to avoid stale field values.
	"""
	pos_profile_name = _resolve_pos_profile_name()

	# Mania: Always fetch a fresh doc to ensure latest fields -> Issue reported 04/11/2025
	pos_profile_doc = frappe.get_doc("POS Profile", pos_profile_name)
	pos_profile_doc.warehouse = requested_warehouse(pos_profile_doc) or pos_profile_doc.warehouse
	return pos_profile_doc


def get_current_pos_profile_lite(fields):
	"""Return only the requested POS Profile fields as a frappe._dict.

	Avoids loading the full document (parent row + every child table: taxes,
	item_groups, payments, …) on latency-critical paths that need just a few
	scalar fields, e.g. barcode/identifier scan lookups. Values are read live
	from the DB, so field freshness matches get_current_pos_profile.
	"""
	pos_profile_name = _resolve_pos_profile_name()
	extra = ["name", "warehouse", "company", "allow_warehouse_change"] if "warehouse" in fields else []
	values = frappe.db.get_value(
		"POS Profile", pos_profile_name, list(dict.fromkeys([*fields, *extra])), as_dict=True
	)
	values = values or frappe._dict()
	if "warehouse" in fields and values:
		values.warehouse = requested_warehouse(values) or values.warehouse
	return values


def forget_deleted_shift(doc, method=None):
	"""after_delete on POS Opening Entry: the series steps back, so the next shift takes this
	name - and must not resolve to the till this one was on."""
	cache = _till_cache()
	for key in [k for k in cache if k.endswith(f"|{doc.name}")]:
		cache.pop(key, None)


def clear_pos_profile_cache(user=None):
	"""Forget the tills cached for `user` (default: the session user)."""
	cache = _till_cache()
	prefix = f"{user or frappe.session.user}|"
	for key in [k for k in cache if k.startswith(prefix)]:
		del cache[key]


def get_user_default_company():
	user = frappe.session.user
	return frappe.defaults.get_user_default(user, "Company")
