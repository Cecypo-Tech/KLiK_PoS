import frappe

OLD = "restrict_cost_visibility_in_tooltip"
NEW = "custom_cost_display"


def execute():
	"""The Hide Cost Price tick became the Cost Display choice: a ticked till stays Hidden,
	an unticked one keeps seeing valuation. Then the tick is dropped."""
	field = frappe.db.get_value("Custom Field", {"dt": "POS Profile", "fieldname": OLD}, "name")
	if not field:
		return
	# The field installer runs after_migrate, after patches: make the new field now.
	from klik_pos.setup.pos_profile_fields import install_pos_profile_feature_fields

	install_pos_profile_feature_fields()
	if frappe.db.has_column("POS Profile", OLD):
		for name, hidden in frappe.get_all("POS Profile", fields=["name", OLD], as_list=True):
			mode = "Hidden" if hidden else "Valuation"
			frappe.db.set_value("POS Profile", name, NEW, mode, update_modified=False)
	frappe.delete_doc("Custom Field", field, ignore_permissions=True)
	frappe.clear_cache(doctype="POS Profile")
