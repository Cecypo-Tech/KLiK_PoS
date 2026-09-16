"""Which shift a cashier is working in.

A till (POS Profile) runs one shift at a time. The cashier who opens it owns the POS Opening
Entry; everyone else on the till joins it. Joining is remembered as a user default and is
honoured only while that entry is still Open, so closing the shift releases everyone at once
with nothing to clean up.
"""

import frappe
from frappe import _

JOINED_SHIFT_KEY = "klik_pos_joined_shift"


def open_shift_on_till(pos_profile):
	rows = frappe.get_all(
		"POS Opening Entry",
		filters={"pos_profile": pos_profile, "docstatus": 1, "status": "Open"},
		fields=["name", "user", "period_start_date"],
		order_by="period_start_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def joined_shift(user=None):
	user = user or frappe.session.user
	entry = frappe.defaults.get_user_default(JOINED_SHIFT_KEY, user)
	if not entry:
		return None
	still_open = frappe.db.get_value(
		"POS Opening Entry", {"name": entry, "docstatus": 1, "status": "Open"}, "name"
	)
	return still_open or None


@frappe.whitelist()
def join_shift(pos_profile):
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

	open_shift = open_shift_on_till(pos_profile)
	if not open_shift:
		frappe.throw(_("No shift is open on {0}. Open one instead.").format(pos_profile))
	frappe.defaults.set_user_default(JOINED_SHIFT_KEY, open_shift.name, user)

	from klik_pos.klik_pos.utils import clear_pos_profile_cache

	clear_pos_profile_cache(user=user)
	return {"success": True, "entry": open_shift.name}
