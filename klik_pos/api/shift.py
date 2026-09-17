"""Which shift a cashier is working in.

A till (POS Profile) runs one shift at a time. The cashier who opens it owns the POS Opening
Entry; everyone else on the till joins it. Joining is remembered as a user default and is
honoured only while that entry is still Open, so closing the shift releases everyone at once
with nothing to clean up.
"""

import frappe
from frappe import _

JOINED_SHIFT_KEY = "klik_pos_joined_shift"

# The set of roles that may close a shift that isn't theirs, when it is stale or one of
# several open on a till. klik_pos.api.payment._check_admin_privileges uses the same set,
# via is_shift_manager, so the two can't drift apart.
SHIFT_MANAGER_ROLES = {"Administrator", "System Manager", "Sales Manager"}


def is_shift_manager(user=None):
	return bool(SHIFT_MANAGER_ROLES & set(frappe.get_roles(user or frappe.session.user)))


def _is_stale(row):
	return frappe.utils.get_date_str(row.period_start_date) != frappe.utils.today()


def open_shifts_on_till(pos_profile):
	"""Every Open shift on `pos_profile`, oldest first. The name tie-breaks shifts opened in
	the same instant, so callers that pick "the oldest" get a stable answer."""
	return frappe.get_all(
		"POS Opening Entry",
		filters={"pos_profile": pos_profile, "docstatus": 1, "status": "Open"},
		fields=["name", "user", "period_start_date"],
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
		["name", "period_start_date"],
		as_dict=True,
	)
	if not row:
		return None
	# A shift a cashier joined stops being "theirs" the moment it goes stale: only a manager
	# may still act in it, so an ordinary cashier is treated as no longer joined at all.
	if _is_stale(row) and not is_shift_manager(user):
		return None
	return row.name


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
		raise frappe.PermissionError(_("You are not assigned to POS Profile {0}.").format(pos_profile))

	own_shift = frappe.db.exists(
		"POS Opening Entry", {"user": user, "docstatus": 1, "status": "Open"}
	)
	if own_shift:
		frappe.throw(_("Close your own shift {0} before joining another.").format(own_shift))

	if frappe.db.get_value("POS Profile", pos_profile, "disabled"):
		frappe.throw(_("POS Profile {0} is disabled.").format(pos_profile))

	shifts = open_shifts_on_till(pos_profile)

	if entry:
		if not is_shift_manager(user):
			raise frappe.PermissionError(_("Only a manager can choose which shift to close."))
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
		if _is_stale(chosen) and not is_shift_manager(user):
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
