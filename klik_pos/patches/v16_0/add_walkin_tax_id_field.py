import frappe

from klik_pos.setup.walkin_fields import WALKIN_DOCTYPES, install_walkin_fields


def execute():
	"""Add Walk-in Tax ID wherever the walk-in fields were already installed (by the POS
	Profile button), so existing sites get it on migrate. New setups get it from the button."""
	doctypes = [
		dt for dt in WALKIN_DOCTYPES
		if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "custom_walkin_customer_name"})
	]
	if doctypes:
		install_walkin_fields(doctypes)
