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
def partial_payment(profile_name, allowed):
	"""Pin POS Profile.allow_partial_payment for the block, restoring it afterwards.

	It has to be a DB write: ERPNext reads the flag from the invoice's linked POS Profile
	during validation, so patching a cached profile object never reaches it.
	"""
	original = frappe.db.get_value("POS Profile", profile_name, "allow_partial_payment")
	frappe.db.set_value("POS Profile", profile_name, "allow_partial_payment", 1 if allowed else 0)
	frappe.db.commit()
	try:
		yield
	finally:
		frappe.db.set_value("POS Profile", profile_name, "allow_partial_payment", original)
		frappe.db.commit()
