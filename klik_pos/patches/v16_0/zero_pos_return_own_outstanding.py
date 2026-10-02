import frappe


def execute():
	"""A POS return applied to its original (update_outstanding_for_self off) books its
	Debtors legs against the original, but ERPNext left -grand_total in the return's own
	outstanding_amount, so its credit read as still owed. Reset each such return to what the
	ledger holds against it - nothing, unless something was since reconciled to it."""
	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice` si
		SET si.outstanding_amount = COALESCE((
			SELECT SUM(ple.amount_in_account_currency)
			FROM `tabPayment Ledger Entry` ple
			WHERE ple.against_voucher_type = 'Sales Invoice'
				AND ple.against_voucher_no = si.name
				AND ple.delinked = 0
		), 0)
		WHERE si.docstatus = 1
			AND si.is_return = 1
			AND si.is_pos = 1
			AND IFNULL(si.return_against, '') != ''
			AND si.update_outstanding_for_self = 0
			AND si.outstanding_amount != 0
		"""
	)
