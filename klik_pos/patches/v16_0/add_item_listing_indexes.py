import frappe


def execute():
	"""Indexes the till's item listing leans on.

	Product Bundle (new_item_code, disabled): every listing page asks "is this item a bundle?"
	by new_item_code, which had no index (each check scanned the table). Two columns on
	purpose: Frappe's schema sync drops a single-column index on a field the DocType does not
	mark search_index, and leaves a composite alone. Item (item_group, item_name): a category
	page walks one group in name order instead of filtering the whole name index.
	"""
	frappe.db.add_index(
		"Product Bundle", ["new_item_code", "disabled"], index_name="klik_pos_bundle_item_disabled"
	)
	frappe.db.add_index("Item", ["item_group", "item_name"], index_name="klik_pos_item_group_name")
