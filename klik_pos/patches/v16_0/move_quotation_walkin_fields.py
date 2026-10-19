import frappe

from klik_pos.setup.walkin_fields import install_walkin_fields


def execute():
	"""Move Quotation's walk-in fields up beside the customer where the button installed them."""
	if frappe.db.exists("Custom Field", {"dt": "Quotation", "fieldname": "custom_walkin_customer_name"}):
		install_walkin_fields(["Quotation"])
