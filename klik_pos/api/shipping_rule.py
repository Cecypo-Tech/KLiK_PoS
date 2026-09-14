import frappe

from klik_pos.api.sales_invoice import _get_active_pos_profile


@frappe.whitelist()
def get_shipping_rules():
	"""Selling Shipping Rules the active till's company can charge at checkout."""
	pos_profile = _get_active_pos_profile()
	return frappe.get_all(
		"Shipping Rule",
		filters={"company": pos_profile.company, "shipping_rule_type": "Selling", "disabled": 0},
		fields=["name", "label", "calculate_based_on", "shipping_amount"],
		order_by="label asc",
	)
