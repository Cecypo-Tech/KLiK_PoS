"""Which shift a cashier is working in.

A till (POS Profile) runs one shift at a time. The cashier who opens it owns the POS Opening
Entry; everyone else on the till joins it. The shift a cashier works in - one they opened or
joined - is remembered as a user default and is honoured only while that entry is still
Open, so closing the shift releases everyone at once with nothing to clean up.

A cashier may own an open shift on one till while working on another: Switch profile
(leave_shift) steps out of a shift and leaves it open for whoever is still in it, or for a
manager, to close.
"""

import frappe
from frappe import _

# The shift the cashier works in. Named for joining, which came first; opening a shift sets
# it too (pos_entry.remember_opened_shift).
JOINED_SHIFT_KEY = "klik_pos_joined_shift"
# Stepped out of every shift: the cashier picks a till again, even if one they opened is open.
LEFT_SHIFT = "__left__"

from klik_pos.api.user import ADMIN_ROLES

# Roles that may close a shift that isn't theirs, when it is stale or one of several open on
# a till. The data-scope admins, plus Express Admin: an ERPNext Express manager holds only
# that role and can't be given a standard one. Closing a till is not a licence to see every
# till's figures, so the payment summary keeps ADMIN_ROLES alone.
SHIFT_MANAGER_ROLES = {*ADMIN_ROLES, "Express Admin"}


def is_shift_manager(user=None):
	return bool(SHIFT_MANAGER_ROLES & set(frappe.get_roles(user or frappe.session.user)))


DAILY_CLOSE_FIELD = "custom_require_daily_shift_close"


def requires_daily_close(pos_profile):
	"""Whether `pos_profile`'s shift is good only for the day it was opened (ERPNext's rule,
	and the default). Off, an open shift is good until someone closes it."""
	if not pos_profile or not frappe.db.has_column("POS Profile", DAILY_CLOSE_FIELD):
		return True
	# Read on every sale and every shift lookup; the profile's document cache is cleared
	# whenever it is saved.
	value = frappe.get_cached_value("POS Profile", pos_profile, DAILY_CLOSE_FIELD)
	return value is None or bool(value)


CLOSING_FIELD = "custom_allow_closing_shift"


def till_allows_closing(pos_profile):
	"""Whether `pos_profile`'s own users close its shift (the default). Off, only a manager
	does, and the till's users do not see the closing figures."""
	if not pos_profile or not frappe.db.has_column("POS Profile", CLOSING_FIELD):
		return True
	value = frappe.get_cached_value("POS Profile", pos_profile, CLOSING_FIELD)
	return value is None or bool(value)


def may_close_on_till(pos_profile, user=None):
	return till_allows_closing(pos_profile) or is_shift_manager(user)


def ensure_may_close_on_till(pos_profile, user=None):
	if not may_close_on_till(pos_profile, user):
		frappe.throw(
			_("Closing is turned off on {0}. A manager closes this till's shift.").format(pos_profile),
			frappe.PermissionError,
		)


def _is_stale(row):
	"""A shift opened before today, on a till that requires a daily close."""
	if frappe.utils.get_date_str(row.period_start_date) == frappe.utils.today():
		return False
	till = row.get("pos_profile") or frappe.db.get_value("POS Opening Entry", row.name, "pos_profile")
	return requires_daily_close(till)


def open_shifts_on_till(pos_profile):
	"""Every Open shift on `pos_profile`, oldest first. The name tie-breaks shifts opened in
	the same instant, so callers that pick "the oldest" get a stable answer."""
	return frappe.get_all(
		"POS Opening Entry",
		filters={"pos_profile": pos_profile, "docstatus": 1, "status": "Open"},
		fields=["name", "user", "pos_profile", "period_start_date"],
		order_by="period_start_date asc, name asc",
	)


def joined_shift(user=None):
	user = user or frappe.session.user
	entry = frappe.defaults.get_user_default(JOINED_SHIFT_KEY, user)
	if not entry:
		return None
	row = frappe.db.get_value(
		"POS Opening Entry",
		{"name": entry, "docstatus": 1, "status": "Open"},
		["name", "pos_profile", "period_start_date", "user"],
		as_dict=True,
	)
	if not row:
		return None
	# A shift a cashier joined stops being "theirs" the moment it goes stale: only a manager
	# may still act in it, so an ordinary cashier is treated as no longer joined at all. Their
	# own stays theirs, so it routes them to closing it.
	if _is_stale(row) and row.user != user and not is_shift_manager(user):
		return None
	return row.name


@frappe.whitelist()
def leave_shift():
	"""Step out of the shift the caller works in, to pick another of their tills.

	The shift stays open: anyone still in it, or a manager, closes it. Its opener can come
	back to it by picking that till again."""
	user = frappe.session.user
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry

	if get_current_pos_opening_entry():
		frappe.defaults.set_user_default(JOINED_SHIFT_KEY, LEFT_SHIFT, user)

	from klik_pos.klik_pos.utils import clear_pos_profile_cache

	clear_pos_profile_cache(user=user)
	return {"success": True}


@frappe.whitelist()
def join_shift(pos_profile, entry=None):
	"""Join the shift open on `pos_profile`.

	Without `entry`, joins the till's single Open shift - refused if there is more than one,
	or if the one shift is stale and the caller is not a manager (a manager joining a stale
	shift this way is how they get into it to close it). With `entry`, a manager picks which
	of several Open shifts to join; anyone else is refused outright.
	"""
	user = frappe.session.user
	if not frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": user}):
		frappe.throw(
			_("You are not assigned to POS Profile {0}.").format(pos_profile), frappe.PermissionError
		)

	if frappe.db.get_value("POS Profile", pos_profile, "disabled"):
		frappe.throw(_("POS Profile {0} is disabled.").format(pos_profile))

	shifts = open_shifts_on_till(pos_profile)

	if entry:
		if not is_shift_manager(user):
			frappe.throw(_("Only a manager can choose which shift to close."), frappe.PermissionError)
		chosen = next((row for row in shifts if row.name == entry), None)
		if not chosen:
			frappe.throw(_("{0} is not an open shift on {1}.").format(entry, pos_profile))
	else:
		if not shifts:
			frappe.throw(_("No shift is open on {0}. Open one instead.").format(pos_profile))
		if len(shifts) > 1:
			frappe.throw(
				_("Till {0} has {1} open shifts. A manager must close the extra shifts first.").format(
					pos_profile, len(shifts)
				)
			)
		chosen = shifts[0]
		# Their own stale shift a cashier may re-enter, to close it.
		if _is_stale(chosen) and chosen.user != user and not is_shift_manager(user):
			frappe.throw(
				_(
					"Shift {0} on {1} was opened on {2} by {3}. A manager must close it before "
					"this till can sell."
				).format(
					chosen.name,
					pos_profile,
					frappe.utils.get_date_str(chosen.period_start_date),
					frappe.db.get_value("User", chosen.user, "full_name") or chosen.user,
				)
			)

	frappe.defaults.set_user_default(JOINED_SHIFT_KEY, chosen.name, user)

	from klik_pos.klik_pos.utils import clear_pos_profile_cache

	clear_pos_profile_cache(user=user)
	return {"success": True, "entry": chosen.name}
