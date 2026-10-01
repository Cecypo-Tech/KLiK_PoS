import frappe


def execute():
	"""queue_status shipped with default "Queued", so every Sales Invoice started out "Queued"
	and only the background worker ever changed it. An invoice the queue never saw - its
	enable_background_invoice_submission is 0 - has no queue status at all. A queued sale that
	went through but still reads "Queued" reads "Submitted"."""
	if not frappe.db.has_column("Sales Invoice", "queue_status"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET queue_status = ''
		WHERE queue_status = 'Queued'
			AND IFNULL(enable_background_invoice_submission, 0) = 0
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET queue_status = 'Submitted'
		WHERE queue_status = 'Queued'
			AND docstatus IN (1, 2)
			AND enable_background_invoice_submission = 1
		"""
	)
