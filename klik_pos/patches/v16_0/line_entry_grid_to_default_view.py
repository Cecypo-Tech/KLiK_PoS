import frappe


def execute():
	"""The Line Entry Grid tick became a Default View option: carry each ticked till over,
	then drop the tick."""
	field = "POS Profile-custom_line_entry_grid"
	if not frappe.db.exists("Custom Field", field):
		return
	if frappe.db.has_column("POS Profile", "custom_line_entry_grid"):
		for name in frappe.get_all("POS Profile", {"custom_line_entry_grid": 1}, pluck="name"):
			frappe.db.set_value("POS Profile", name, "custom_default_view", "Line Entry View", update_modified=False)
	frappe.delete_doc("Custom Field", field, ignore_permissions=True)
