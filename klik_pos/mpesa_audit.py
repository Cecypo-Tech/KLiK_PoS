"""Read-only checks for M-Pesa money shapes that should never exist.

Tests cover the cases someone thought of; this looks at what actually happened.
Run: bench --site <site> execute klik_pos.mpesa_audit.run --kwargs "{'since': '2026-10-01'}"
Every check is a SELECT. Each key maps to the offending rows; empty means clean. Without
`since` it looks at the last 30 days: older register history from earlier flows would
otherwise bury what is new. Each check returns at most `limit` rows (default 200).
"""

import frappe
from frappe.utils import add_days, nowdate

from klik_pos.api.sales_invoice import SITE_SALE_TYPE_FIELD, _site_sale_types

TOL = 0.01


def run(since: str | None = None, limit: int = 200) -> dict:
	if not frappe.db.has_column("Payment Entry", "custom_mpesa_receipt_number"):
		frappe.throw("Payment Entry has no custom_mpesa_receipt_number column; run bench migrate with klik_pos installed.")
	since = since or add_days(nowdate(), -30)
	args = {"since": since, "tol": TOL, "limit": int(limit)}
	owing = """
		SELECT si.name, si.customer, si.posting_date, si.grand_total, si.outstanding_amount
		FROM `tabSales Invoice` si
		WHERE si.docstatus=1 AND si.is_pos=1 AND si.is_return=0
		  AND si.outstanding_amount > %(tol)s AND si.posting_date >= %(since)s
	"""
	out = {}
	if {"Cash", "Credit"} <= _site_sale_types():
		# Allparts: a Cash sale must be paid in full; Credit sales may owe. One with no type
		# (older, desk or imported) can be either, so a person decides.
		field = f"si.`{SITE_SALE_TYPE_FIELD}`"
		out["short_paid_cash_sale"] = frappe.db.sql(owing + f" AND {field}='Cash' LIMIT %(limit)s", args, as_dict=True)
		out["owing_pos_sale_check_by_hand"] = frappe.db.sql(
			owing + f" AND IFNULL({field}, '') NOT IN ('Cash', 'Credit') LIMIT %(limit)s", args, as_dict=True
		)
	else:
		out["short_paid_cash_sale"] = []
		out["owing_pos_sale_check_by_hand"] = frappe.db.sql(owing + " LIMIT %(limit)s", args, as_dict=True)

	out["overdrawn_receipt"] = frappe.db.sql(
		"""
		SELECT pe.name, pe.custom_mpesa_receipt_number AS transid, pe.paid_amount, pe.unallocated_amount,
		       COALESCE(SUM(ref.allocated_amount), 0) AS allocated
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabPayment Entry Reference` ref ON ref.parent = pe.name
		WHERE pe.docstatus=1 AND IFNULL(pe.custom_mpesa_receipt_number, '') != '' AND pe.posting_date >= %(since)s
		GROUP BY pe.name
		HAVING pe.unallocated_amount < -%(tol)s OR allocated > pe.paid_amount + %(tol)s
		LIMIT %(limit)s
		""",
		args,
		as_dict=True,
	)

	out["receipt_with_several_entries"] = frappe.db.sql(
		"""
		SELECT custom_mpesa_receipt_number AS name, COUNT(*) AS entries, GROUP_CONCAT(name) AS payment_entries
		FROM `tabPayment Entry`
		WHERE docstatus=1 AND IFNULL(custom_mpesa_receipt_number, '') != '' AND posting_date >= %(since)s
		GROUP BY custom_mpesa_receipt_number HAVING COUNT(*) > 1
		LIMIT %(limit)s
		""",
		args,
		as_dict=True,
	)

	out["receipt_over_allocated_on_invoices"] = frappe.db.sql(
		"""
		SELECT m.mpesa_c2b_payment_register AS name, reg.transid, reg.transamount,
		       SUM(m.allocated_amount) AS allocated, GROUP_CONCAT(si.name) AS invoices
		FROM `tabPOS Mpesa Reconciled Payment` m
		JOIN `tabSales Invoice` si ON si.name = m.parent AND m.parenttype = 'Sales Invoice'
		JOIN `tabMpesa C2B Payment Register` reg ON reg.name = m.mpesa_c2b_payment_register
		-- A return copies its sale's trace rows; counting both would double the receipt.
		WHERE si.docstatus=1 AND si.is_return=0 AND si.posting_date >= %(since)s
		GROUP BY m.mpesa_c2b_payment_register
		HAVING allocated > reg.transamount + %(tol)s
		LIMIT %(limit)s
		""",
		args,
		as_dict=True,
	)

	out["consumed_row_without_entry"] = frappe.db.sql(
		"""
		SELECT reg.name, reg.transid, reg.transamount, reg.payment_entry
		FROM `tabMpesa C2B Payment Register` reg
		LEFT JOIN `tabPayment Entry` pe ON pe.name = reg.payment_entry
		WHERE reg.docstatus=1 AND reg.posting_date >= %(since)s AND IFNULL(pe.docstatus, 0) != 1
		  -- A receipt klik took (it has a trace row) is always paid through an entry. One it
		  -- did not is booked elsewhere: STK push and the M-Pesa app's quick-pay put the money
		  -- on a submitted sale's M-Pesa rows (rows naming the receipt or its push request, or
		  -- the sale the register names), and a push against an order or payment request gets
		  -- its own entry. It counts only when the whole receipt is there; a 1000 push on a 500
		  -- row leaves 500 of the customer's money booked nowhere.
		  AND (
			EXISTS (SELECT 1 FROM `tabPOS Mpesa Reconciled Payment` m WHERE m.mpesa_c2b_payment_register = reg.name)
			OR (
				COALESCE((
					SELECT SUM(p.amount) FROM `tabSales Invoice Payment` p
					JOIN `tabSales Invoice` s ON s.name = p.parent AND s.docstatus = 1 AND s.is_return = 0
					WHERE s.name = reg.sales_invoice AND p.mode_of_payment = reg.mode_of_payment
				), 0) < reg.transamount - %(tol)s
				AND COALESCE((
					SELECT SUM(p.amount) FROM `tabSales Invoice Payment` p
					JOIN `tabSales Invoice` s ON s.name = p.parent AND s.docstatus = 1 AND s.is_return = 0
					WHERE p.reference_no IN (NULLIF(reg.transid, ''), reg.name)
					   OR p.custom_reference_text IN (NULLIF(reg.transid, ''), reg.name)
					   OR p.reference_no IN (SELECT r.name FROM `tabMpesa Express Request` r WHERE r.transaction_id = NULLIF(reg.transid, ''))
					   OR p.custom_reference_text IN (SELECT r.name FROM `tabMpesa Express Request` r WHERE r.transaction_id = NULLIF(reg.transid, ''))
				), 0) < reg.transamount - %(tol)s
				AND NOT EXISTS (
					SELECT 1 FROM `tabPayment Entry` x
					WHERE x.docstatus = 1 AND x.reference_no = NULLIF(reg.transid, '') AND x.paid_amount >= reg.transamount - %(tol)s
				)
			)
		  )
		LIMIT %(limit)s
		""",
		args,
		as_dict=True,
	)

	for key, rows in out.items():
		print(f"{key}: {len(rows)}" + (" (capped)" if len(rows) >= args["limit"] else ""))
	return out
