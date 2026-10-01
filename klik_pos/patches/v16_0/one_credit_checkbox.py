import frappe

OLD = "custom_allow_credit_sales"  # 2025-08; the switch since f5a31b4 (2026-09-30)
KEPT = "custom_allow_credit_sales_as_pos"  # 2026-07; how an allowed credit sale was booked
# Inlined, so migrating an old backup never depends on a constant elsewhere being renamed.
LABEL = "Allow Credit Sales"
DESCRIPTION = (
	"Lets cashiers sell on credit: an unpaid invoice with a due date, for a named customer. "
	"Credit sales are booked as POS sales and count in the till's shift."
)


def execute():
	"""Leave one credit checkbox on the POS Profile: KEPT becomes the switch.

	Each till keeps the credit permission it has today. Where OLD has been the switch -
	the site ran f5a31b4 and 2f28226, which showed it - KEPT takes OLD's value. Where it never
	was - OLD still hidden, unread - credit followed "Allow Partial Payment", so KEPT takes
	that. Every till whose value changes is printed, for the record.
	"""
	old_field = frappe.db.get_value(
		"Custom Field", {"dt": "POS Profile", "fieldname": OLD}, ["name", "hidden"], as_dict=True
	)
	if old_field:
		_ensure_kept_field()
		carry_over_permission(source=OLD if not old_field.hidden else "allow_partial_payment")
		frappe.delete_doc("Custom Field", old_field.name, ignore_permissions=True)

	kept_field = frappe.db.get_value("Custom Field", {"dt": "POS Profile", "fieldname": KEPT}, "name")
	if kept_field:
		frappe.db.set_value("Custom Field", kept_field, {"label": LABEL, "description": DESCRIPTION})
	frappe.clear_cache(doctype="POS Profile")


def _ensure_kept_field():
	"""KEPT is created by after_migrate, which runs after patches: on a site that never had
	it, create it now, or the permission would be dropped before it exists."""
	if not frappe.db.has_column("POS Profile", KEPT):
		from klik_pos.setup.pos_profile_fields import install_pos_profile_feature_fields

		install_pos_profile_feature_fields()


def carry_over_permission(source):
	"""Set KEPT from `source` on every till, printing each one that changes."""
	if not frappe.db.has_column("POS Profile", source):
		return
	for till in frappe.get_all("POS Profile", fields=["name", f"`{source}` as permission", f"`{KEPT}` as kept"]):
		allowed = 1 if till.permission else 0
		if (till.kept or 0) != allowed:
			print(f"one_credit_checkbox: {till.name}: Allow Credit Sales {till.kept or 0} -> {allowed} (from {source})")
			frappe.db.set_value("POS Profile", till.name, KEPT, allowed, update_modified=False)
