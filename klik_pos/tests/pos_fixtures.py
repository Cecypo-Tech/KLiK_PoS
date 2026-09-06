"""Fixtures that pin what the checkout tests depend on.

Three separate ambient-config breakages traced back to this file not existing.
"""

import contextlib

import frappe


def pick_payment_mode(profile_name):
	"""A deterministic mode of payment for a POS Profile.

	`frappe.db.get_value("POS Payment Method", {"parent": ...}, "mode_of_payment")` is
	UNORDERED. With one payment method on the profile it looks stable; add a few and it
	silently starts returning a different mode. Prefer the profile's default, then the
	lowest idx. Never reintroduce the unordered get_value.
	"""
	rows = frappe.get_all(
		"POS Payment Method",
		filters={"parent": profile_name, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "`default`", "idx"],
		order_by="idx asc",
	)
	if not rows:
		return None
	for row in rows:
		if row.get("default"):
			return row["mode_of_payment"]
	return rows[0]["mode_of_payment"]


def payable_total(customer, items, mode_of_payment):
	"""What the checkout will actually demand for `items` - not the sum of line prices.

	A company-wide default Sales Taxes and Charges Template (`Kenya Tax - DC` on this
	bench) adds tax the payload never mentions, so paying the line price produces a
	PARTIALLY PAID invoice. That passes while the POS Profile allows partial payment and
	fails the moment it does not. Ask the builder rather than assuming a tax rate, so the
	tests hold whether or not a default template exists.
	"""
	from klik_pos.api.sales_invoice import build_sales_invoice_doc

	doc = build_sales_invoice_doc(customer, items, 0, None, mode_of_payment, "B2C", include_payments=False)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	return doc.rounded_total or doc.grand_total


@contextlib.contextmanager
def pos_profile_settings(profile_name, **values):
	"""Pin POS Profile fields for the block, restoring them afterwards - even on failure.

	It has to be a DB write: ERPNext reads the profile from the invoice's link during
	validation (`set_pos_fields`, the partial-payment check), so patching a cached profile
	object never reaches it. Two fields have bitten so far:

	- allow_partial_payment: gates any underpaid sale.
	- taxes_and_charges: `set_pos_fields` copies it onto every POS invoice, blanking a
	  company-default template while leaving its tax rows behind. erpnext_express then
	  rejects "tax rows without a template" for any user with an Express role - so a
	  cashier cannot sell at all on a profile with no template, while Administrator can.
	"""
	original = frappe.db.get_value("POS Profile", profile_name, list(values), as_dict=True)
	for field, value in values.items():
		frappe.db.set_value("POS Profile", profile_name, field, value)
	frappe.db.commit()
	try:
		yield
	finally:
		for field in values:
			frappe.db.set_value("POS Profile", profile_name, field, original[field])
		frappe.db.commit()


def default_sales_tax_template(company):
	"""The company's default Sales Taxes and Charges Template, or None."""
	return frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": company, "is_default": 1}, "name"
	)
