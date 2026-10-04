import frappe


def execute():
	"""Indexes the till's item listing leans on.

	Product Bundle: every listing page asks "is this item a bundle?" by new_item_code, which
	had no index (each check scanned the table). Item (item_group, item_name): a category
	page walks one group in name order instead of filtering the whole name index.
	"""
	frappe.db.add_index("Product Bundle", ["new_item_code"], index_name="klik_pos_bundle_item_code")
	frappe.db.add_index("Item", ["item_group", "item_name"], index_name="klik_pos_item_group_name")
