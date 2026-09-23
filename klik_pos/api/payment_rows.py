"""Which Payment Entries settled an invoice - read once, shared by every surface.

M-Pesa money arrives on the invoice as advances from Payment Entries, so the payments
table shows the mode with no amount. The invoice list, the detail page and the receipt
all need the money, the receipt number and the phone; this is the one place they get it.
"""

import frappe
from frappe.utils import flt


def advance_payment_rows(invoice_names) -> dict:
	"""{invoice: [{mode_of_payment, paid_to, amount, reference_no, phone_number, payment_entry}]}.

	Only invoices that have at least one allocated Payment Entry advance appear as keys, so
	callers can fall back to the payments table with a plain .get().

	A Payment Entry need not carry a Mode of Payment - one made outside the POS (a customer
	advance an accountant recorded) usually has none. A mode is only a name for an account,
	so such a row takes the mode whose default account for the company is paid_to, the
	account the money went to (see _mode_for_account); the list, the filter and the
	Closing Shift then treat it as any other payment. When no mode points at that account
	the mode stays blank - never the account name, because the Closing Shift turns every
	mode it sees into a POS Closing Entry Detail row, whose mode is a Link to Mode of
	Payment - and mode_label() shows paid_to instead so the money does not vanish.

	pos_opening_entry is the shift the Payment Entry itself was stamped with (M-Pesa
	receipts are); the closing reconciliation counts those through their own shift and
	uses it to avoid counting them again here.

	Only submitted entries on a live invoice count. ERPNext leaves the advance rows behind
	on a cancelled invoice - it deletes them only when a single payment is unlinked - so
	without the docstatus filters a cancelled sale would still read as paid by M-Pesa.
	"""
	if not invoice_names:
		return {}
	# The phone number is a custom field installed by frappe_mpsa_payments' own patch.
	# Selecting it on a site that has not got it would turn every invoice list and detail
	# page into a 500, so the whole surface degrades to "no phone" instead.
	phone = (
		"pe.custom_mpesa_phone_number AS phone_number"
		if frappe.db.has_column("Payment Entry", "custom_mpesa_phone_number")
		else "NULL AS phone_number"
	)
	stamped_shift = (
		"pe.custom_pos_opening_entry AS pos_opening_entry"
		if frappe.db.has_column("Payment Entry", "custom_pos_opening_entry")
		else "NULL AS pos_opening_entry"
	)
	rows = frappe.db.sql(
		f"""
		SELECT adv.parent, adv.reference_name AS payment_entry, adv.allocated_amount AS amount,
			pe.mode_of_payment, pe.paid_to, pe.reference_no, {phone}, {stamped_shift},
			si.company, si.pos_profile
		FROM `tabSales Invoice Advance` adv
		INNER JOIN `tabPayment Entry` pe ON pe.name = adv.reference_name
		INNER JOIN `tabSales Invoice` si ON si.name = adv.parent
		WHERE adv.parenttype = 'Sales Invoice'
			AND adv.parent IN %(names)s
			AND adv.reference_type = 'Payment Entry'
			AND adv.allocated_amount > 0
			AND pe.docstatus = 1
			AND si.docstatus != 2
		ORDER BY adv.parent, adv.idx
		""",
		{"names": tuple(invoice_names)},
		as_dict=True,
	)
	resolve = _mode_for_account(rows)
	out: dict = {}
	for row in rows:
		out.setdefault(row.parent, []).append(
			{
				"mode_of_payment": row.mode_of_payment or resolve(row),
				"paid_to": row.paid_to,
				"amount": flt(row.amount),
				"reference_no": row.reference_no,
				"phone_number": row.phone_number,
				"payment_entry": row.payment_entry,
				"pos_opening_entry": row.pos_opening_entry or None,
			}
		)
	return out


def _mode_for_account(rows):
	"""row -> the Mode of Payment to count a mode-less Payment Entry under, or None.

	Candidates are the modes whose default account for the invoice's company is the
	entry's paid_to. Several modes can share one account (Cash and Bank Draft both post
	to the cash account), so the till that rang the sale settles it: a mode in its POS
	Profile's payment list wins, in the till's order; failing that, the first by name.
	Looked up once per call for every (company, account) and profile the rows need.
	"""
	pairs = {(r.company, r.paid_to) for r in rows if not r.mode_of_payment and r.paid_to}
	if not pairs:
		return lambda row: None

	by_account: dict = {}
	for r in frappe.db.sql(
		"""
		SELECT mpa.company, mpa.default_account, mpa.parent AS mode
		FROM `tabMode of Payment Account` mpa
		INNER JOIN `tabMode of Payment` mop ON mop.name = mpa.parent AND mop.enabled = 1
		WHERE (mpa.company, mpa.default_account) IN %(pairs)s
		ORDER BY mpa.parent
		""",
		{"pairs": tuple(pairs)},
		as_dict=True,
	):
		by_account.setdefault((r.company, r.default_account), []).append(r.mode)

	profiles = {r.pos_profile for r in rows if r.pos_profile}
	till_modes: dict = {}
	if profiles:
		for r in frappe.get_all(
			"POS Payment Method",
			filters={"parenttype": "POS Profile", "parent": ("in", list(profiles))},
			fields=["parent", "mode_of_payment"],
			order_by="parent, idx",
		):
			till_modes.setdefault(r.parent, []).append(r.mode_of_payment)

	def resolve(row):
		candidates = by_account.get((row.company, row.paid_to), [])
		if not candidates:
			return None
		for mode in till_modes.get(row.pos_profile, []):
			if mode in candidates:
				return mode
		return candidates[0]

	return resolve


def merge_payment_rows(sip_rows: list, advance_rows: list) -> list:
	"""Payments-table rows plus advance rows, without the placeholder zero rows.

	The zero-amount row exists to satisfy ERPNext and to carry the mode; once the money
	for that mode is here from an advance, showing 'Mpesa 0.00' beside 'Mpesa 450.00'
	would read as two payments.
	"""
	if not advance_rows:
		return list(sip_rows)
	advanced_modes = {r["mode_of_payment"] for r in advance_rows if r.get("mode_of_payment")}
	kept = [r for r in sip_rows if not (flt(r.get("amount")) == 0 and r.get("mode_of_payment") in advanced_modes)]
	return kept + list(advance_rows)


def mode_label(payment_rows: list) -> str:
	"""The 'Cash/Mpesa' label a list shows for how an invoice was paid.

	Distinct modes in first-seen order: one row per receipt means several rows share a
	mode, and 'Mpesa/Mpesa/Mpesa' would no longer match the Mode of Payment filter. A row
	with no mode - a Payment Entry need not have one - shows the account the money went to
	(paid_to) instead of crashing the join, and an invoice with nothing to show reads as '-'.
	"""
	modes = list(dict.fromkeys(row.get("mode_of_payment") or row.get("paid_to") for row in payment_rows))
	modes = [m for m in modes if m]
	return "/".join(modes) if modes else "-"
