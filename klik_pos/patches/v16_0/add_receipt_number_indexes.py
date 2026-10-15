import frappe


def execute():
	"""Index the two columns a Payment Entry is found by its M-Pesa receipt number on.

	klik stamps custom_mpesa_receipt_number; an entry made in the desk names the receipt in
	reference_no. Every receipt the till lists or allocates is looked up by one or both, and
	neither was indexed. Composite with docstatus (every lookup filters on it) because Frappe's
	schema sync drops a single-column index on a field not marked search_index.
	"""
	frappe.db.add_index("Payment Entry", ["reference_no", "docstatus"], index_name="klik_pos_pe_reference_no")
	if frappe.db.has_column("Payment Entry", "custom_mpesa_receipt_number"):
		frappe.db.add_index(
			"Payment Entry",
			["custom_mpesa_receipt_number", "docstatus"],
			index_name="klik_pos_pe_mpesa_receipt_number",
		)
