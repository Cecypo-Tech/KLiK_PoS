import frappe


def execute():
	"""Point each STK-paid register row at the sale its push paid.

	A held-order push's C2B confirmation is consumed while the push still names the order,
	so the row was left naming no sale; checkout then pointed the push at the invoice but
	not the row (fixed in mpesa_order._hand_over_to_invoice). Only rows with no Payment
	Entry and no sale are filled, and only with an invoice that exists, so a rerun changes
	nothing.
	"""
	if not frappe.db.table_exists("Mpesa C2B Payment Register") or not frappe.db.has_column(
		"Mpesa C2B Payment Register", "sales_invoice"
	):
		return
	frappe.db.sql(
		"""
		UPDATE `tabMpesa C2B Payment Register` reg
		INNER JOIN `tabMpesa Express Request` req
			ON req.transaction_id = reg.transid AND req.status = 'Completed'
			AND req.reference_doctype = 'Sales Invoice'
		INNER JOIN `tabSales Invoice` si ON si.name = req.reference_name
		SET reg.sales_invoice = req.reference_name
		WHERE reg.docstatus = 1 AND IFNULL(reg.payment_entry, '') = ''
			AND IFNULL(reg.sales_invoice, '') = '' AND IFNULL(reg.transid, '') != ''
		"""
	)
