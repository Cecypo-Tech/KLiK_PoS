"""M-Pesa reconciliation for the POS checkout: a read-only search endpoint plus
the Payment-Entry-first flow that turns selected `Mpesa C2B Payment Register`
rows into money on a Sales Invoice.

`get_mpesa_payments` is a read-only search backing the checkout's "M-Pesa
Payment Options" modal; it queries the register doctype (owned by the
`frappe_mpsa_payments` app) directly via `frappe.get_all`/`frappe.db.count` —
normal, unprivileged, same-site cross-app data access that requires no code
change in the owning app, mirroring the query pattern used by
`cecypo_powerpack.quick_pay.api.list_pending_mpesa_payments`.

Reconciliation itself runs in three phases: `process_mpesa` records the
register rows the cashier selected as trace child rows on the draft invoice;
`_allocate_receipts_before_submit` mints one submitted Payment Entry per
receipt (idempotently) and appends `Sales Invoice Advance` rows FIFO up to
the invoice's payable total, plus a zero-amount payment row per mode, then
saves the draft; after submit, `_finalize_mpesa_reconciliation` reconciles
the advances (ERPNext skips this itself for POS invoices), consumes the
register rows under the `is_manual_reconciliation` guard with `payment_entry`
and `sales_invoice` set, and reports any receipt whose entry still holds
unallocated money. The invariant throughout: one receipt, one Payment Entry,
one bank line — any overpaid remainder simply stays unallocated on that same
entry rather than becoming a separate credit voucher.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt


def _mpesa_shortcodes_for_company(company: str) -> list[str]:
	"""Return all distinct, non-empty M-Pesa business shortcodes configured
	for `company` (a company can have more than one, e.g. paybill + till)."""
	rows = frappe.get_all(
		"Mpesa Settings",
		filters={"company": company},
		fields=["business_shortcode"],
	)
	shortcodes = {str(r["business_shortcode"]) for r in rows if r.get("business_shortcode")}
	return sorted(shortcodes)


@frappe.whitelist()
def get_mpesa_payments(
	company: str,
	pos_profile: str | None = None,
	mode_of_payment: str | None = None,
	search: str | None = None,
) -> dict:
	"""Return pending Mpesa C2B Payment Register rows for `company`, optionally
	filtered by a 3+ character `search` term.

	`mode_of_payment` is accepted for query-string compatibility with the
	frontend but is intentionally NOT used to filter: a pending row's
	`mode_of_payment` is only populated later, via a separate
	`Mpesa C2B Payment Register URL` lookup in that doctype's
	`set_missing_values()`, so it's NULL on most pending rows pre-reconciliation.
	Filtering on it would exclude every unassigned row.
	"""
	shortcodes = _mpesa_shortcodes_for_company(company)
	if not shortcodes:
		return {"count": 0, "payments": [], "shortcodes": []}

	base_filters = {"docstatus": 0, "businessshortcode": ["in", shortcodes]}
	total_count = frappe.db.count("Mpesa C2B Payment Register", base_filters)

	payments = []
	search = (search or "").strip()
	if len(search) >= 3:
		s = f"%{search}%"
		payments = frappe.get_all(
			"Mpesa C2B Payment Register",
			filters=base_filters,
			or_filters=[
				["full_name", "like", s],
				["transid", "like", s],
				["billrefnumber", "like", s],
				["msisdn", "like", s],
			],
			fields=[
				"name",
				"full_name",
				"transamount",
				"transid",
				"msisdn",
				"posting_date",
				"billrefnumber",
				"businessshortcode",
				"creation",
			],
			order_by="creation desc",
			limit_page_length=100,
		)

	return {"count": total_count, "payments": payments, "shortcodes": shortcodes}


@frappe.whitelist()
def process_mpesa(
	doctype: str,
	invoice_name: str,
	customer: str,
	mpesa_payments: str,
	mode_of_payment: str,
	auto_save: int = 1,
	auto_submit: int = 0,
) -> dict:
	"""Record one or more pending `Mpesa C2B Payment Register` rows against a
	draft (unsubmitted) `Sales Invoice`, backing the POS checkout's "Add
	Selected Payments" button in the "M-Pesa Payment Options" modal.

	This does NOT append rows to the invoice's own `payments` child table and
	does NOT consume (submit) the register rows. It only records
	traceability rows on `invoice.custom_mpesa_reconciled_payments` recording
	which register rows the cashier selected and which Mode of Payment to use
	for each. The actual Payment Entry creation + reconciliation against the
	invoice's outstanding amount happens later, once the invoice is actually
	submitted — see `_finalize_mpesa_reconciliation`, called either inline
	here (when `auto_submit=1`) or from `submit_draft_invoice` (the normal
	POS checkout path, which submits separately after this call returns).

	Deferring consumption this way means a held/draft order with Mpesa
	payments selected can still be freely edited or abandoned without ever
	having consumed a real M-Pesa receipt.

	`doctype` is currently only ever "Sales Invoice" — this app never
	targets Sales Order for this flow.
	"""
	if doctype != "Sales Invoice":
		frappe.throw(_("Mpesa reconciliation only supports Sales Invoice, got {0}").format(doctype))

	if not int(auto_save or 0):
		frappe.throw(
			_(
				"auto_save=0 is not supported: process_mpesa always saves the invoice. "
				"Only auto_save=1 is implemented."
			)
		)

	auto_submit = int(auto_submit or 0)

	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus != 0:
		frappe.throw(
			_("Sales Invoice {0} is not a draft (docstatus={1}); Mpesa payments can only be reconciled onto a draft invoice.").format(
				invoice_name, invoice.docstatus
			)
		)
	if invoice.customer != customer:
		frappe.throw(
			_("Sales Invoice {0} belongs to customer {1}, not {2}.").format(
				invoice_name, invoice.customer, customer
			)
		)

	names = [n.strip() for n in (mpesa_payments or "").split(",") if n.strip()]
	if not names:
		frappe.throw(_("No Mpesa register payments were selected."))

	duplicates = sorted({n for n in names if names.count(n) > 1})
	if duplicates:
		frappe.throw(
			_("The same Mpesa register payment was selected more than once: {0}").format(
				", ".join(duplicates)
			)
		)

	register_rows = []
	invalid = []
	for name in names:
		if not frappe.db.exists("Mpesa C2B Payment Register", name):
			invalid.append(_("{0} (not found)").format(name))
			continue
		row = frappe.get_doc("Mpesa C2B Payment Register", name)
		if row.docstatus != 0:
			invalid.append(_("{0} (already consumed, docstatus={1})").format(name, row.docstatus))
			continue
		if not flt(row.transamount) > 0:
			invalid.append(_("{0} (invalid amount: {1})").format(name, row.transamount))
			continue
		register_rows.append(row)

	if invalid:
		frappe.throw(_("Cannot reconcile the following Mpesa payment(s): {0}").format("; ".join(invalid)))

	total_amount = sum(flt(row.transamount) for row in register_rows)

	payments_added = [
		{"mode_of_payment": mode_of_payment, "amount": row.transamount, "reference": row.transid}
		for row in register_rows
	]

	# Traceability only -- the register rows themselves stay untouched
	# (docstatus=0) until the invoice is actually submitted; see
	# `_finalize_mpesa_reconciliation`.
	for row in register_rows:
		invoice.append(
			"custom_mpesa_reconciled_payments",
			{
				"mpesa_c2b_payment_register": row.name,
				"transid": row.transid,
				"amount": row.transamount,
				"msisdn": row.msisdn,
				"mode_of_payment": mode_of_payment,
			},
		)

	invoice.save()

	result = {
		"success": True,
		"payments_added": payments_added,
		"mpesa_payments": [{"name": row.name, "amount": row.transamount} for row in register_rows],
		"total_amount": total_amount,
		"saved": True,
		"submitted": False,
	}

	if auto_submit:
		embed_summary = _allocate_receipts_before_submit(invoice)
		invoice.submit()
		result["submitted"] = True
		result["mpesa_reconciliation"] = _finalize_mpesa_reconciliation(invoice, embed_summary)

	return result


def _pending_mpesa_rows(invoice) -> list:
	"""Recorded `custom_mpesa_reconciled_payments` rows whose underlying
	`Mpesa C2B Payment Register` row is still unconsumed (docstatus=0)."""
	return [
		child
		for child in invoice.get("custom_mpesa_reconciled_payments") or []
		if frappe.db.get_value("Mpesa C2B Payment Register", child.mpesa_c2b_payment_register, "docstatus") == 0
	]


def _stamp_klik_fields(pe, invoice, child):
	"""Everything a later reader needs to find this entry from the shift, the receipt or the phone."""
	updates = {}
	meta = frappe.get_meta("Payment Entry")
	if meta.has_field("custom_pos_opening_entry") and invoice.get("custom_pos_opening_entry"):
		updates["custom_pos_opening_entry"] = invoice.custom_pos_opening_entry
	if meta.has_field("custom_is_created_from_klik"):
		updates["custom_is_created_from_klik"] = 1
	if meta.has_field("custom_mpesa_receipt_number") and child.transid:
		updates["custom_mpesa_receipt_number"] = child.transid
	if meta.has_field("custom_mpesa_phone_number") and child.msisdn:
		updates["custom_mpesa_phone_number"] = child.msisdn
	if updates:
		# The entry is already submitted; these are informational columns with no GL effect.
		frappe.db.set_value("Payment Entry", pe.name, updates, update_modified=False)


def _ensure_receipt_payment_entries(invoice) -> dict:
	"""One submitted Payment Entry per recorded receipt, for the receipt's whole amount.

	Idempotent by construction: a trace row that already names an entry, or a register row
	that does, is reused. That is what makes a checkout retry safe - the first attempt may
	have created the entry and then failed at invoice submit, and the money it recorded is
	real either way.

	Created here rather than by the register's own `submit_payment` so klik controls the
	stamping and so `Mpesa C2B Payment Register.before_submit` cannot allocate the entry to
	whatever its billref happens to match. Returns {register_row_name: payment_entry_name}
	and sets `child.payment_entry` on the draft; the caller saves the draft.

	Only receipts whose register row is still unconsumed are minted, the same filter the
	caller allocates by: a trace row whose receipt was spent elsewhere is stale, and an
	entry for it would be money nothing ever allocates.
	"""
	from frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry import create_payment_entry

	by_register = {}
	for child in _pending_mpesa_rows(invoice):
		register = child.mpesa_c2b_payment_register
		existing = child.payment_entry or frappe.db.get_value(
			"Mpesa C2B Payment Register", register, "payment_entry"
		)
		if existing and frappe.db.get_value("Payment Entry", existing, "docstatus") == 1:
			child.payment_entry = existing
			by_register[register] = existing
			continue

		pe = create_payment_entry(
			invoice.company,
			invoice.customer,
			flt(child.amount),
			invoice.currency,
			child.mode_of_payment,
			party_type="Customer",
			reference_no=child.transid or register,
			reference_date=invoice.posting_date,
			posting_date=invoice.posting_date,
			submit=1,
		)
		_stamp_klik_fields(pe, invoice, child)
		child.payment_entry = pe.name
		by_register[register] = pe.name

	return by_register


def _assert_cancellation_releases_payments():
	"""Refuse to tie money to an invoice on a site that could not untie it.

	ERPNext only unlinks a Payment Entry when the invoice it settled is cancelled if
	Accounts Settings says so; otherwise the cancel is refused outright and the cashier
	is stuck with a wrong invoice they cannot undo. Better to fail here, once, at setup.
	"""
	if not frappe.db.get_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice"):
		frappe.throw(
			_("Accounts Settings > 'Unlink Payment on Cancellation of Invoice' must be enabled for M-Pesa receipts to be reconciled from the POS."),
			frappe.ValidationError,
		)


def _allocate_receipts_before_submit(invoice) -> dict:
	"""Pre-submit phase: settle the draft from the receipts' Payment Entries as advances.

	Each recorded receipt already has (or gets, see _ensure_receipt_payment_entries) a
	Payment Entry for its full amount. This appends one `Sales Invoice Advance` row per
	entry, in selection order, allocating up to what the invoice still owes; ERPNext's
	update_against_document_in_jv reconciles them at submit and the remainder stays
	unallocated on the same entry - the customer's credit, on the voucher that brought the
	money in, matching the one line on the M-Pesa statement.

	A zero-amount payment row per mode is kept because ERPNext refuses a POS invoice with
	no payment rows (validate_pos_paid_amount), and because the invoice list, the detail
	page and the thermal receipt all read the mode from that table.

	Not set_missing_values(): on a draft carrying a real POS Profile it reaches
	set_pos_fields, which rebuilds `payments` from the profile and would wipe the rows
	appended here.
	"""
	empty = {"received_total": 0.0, "allocated_total": 0.0, "by_register": {}}
	if invoice.docstatus != 0:
		frappe.throw(
			_("Cannot allocate Mpesa receipts on {0}: invoice is not a draft (docstatus={1}).").format(
				invoice.name, invoice.docstatus
			)
		)

	children = _pending_mpesa_rows(invoice)
	if not children:
		return empty

	_assert_cancellation_releases_payments()

	by_register = _ensure_receipt_payment_entries(invoice)

	payable = flt(invoice.rounded_total) or flt(invoice.grand_total)
	already_paid = sum(flt(p.amount) for p in invoice.get("payments") or [])
	already_advanced = sum(flt(a.allocated_amount) for a in invoice.get("advances") or [])
	remaining = max(payable - already_paid - already_advanced, 0.0)

	# A retry re-enters here with the advances of the last attempt still on the draft.
	existing_refs = {a.reference_name for a in invoice.get("advances") or []}

	summary = {"received_total": 0.0, "allocated_total": 0.0, "by_register": {}}
	for child in children:
		pe_name = by_register[child.mpesa_c2b_payment_register]
		pe = frappe.get_doc("Payment Entry", pe_name)
		available = flt(pe.unallocated_amount)
		take = min(available, remaining) if remaining > 0 else 0.0
		if take > 0 and pe_name not in existing_refs:
			invoice.append(
				"advances",
				{
					"reference_type": "Payment Entry",
					"reference_name": pe_name,
					"reference_row": None,
					"advance_amount": available,
					"allocated_amount": take,
					"ref_exchange_rate": flt(pe.source_exchange_rate) or 1,
					"remarks": pe.remarks,
				},
			)
			remaining -= take
		child.allocated_amount = take if pe_name not in existing_refs else child.allocated_amount
		summary["received_total"] += flt(child.amount)
		summary["allocated_total"] += flt(child.allocated_amount)
		summary["by_register"][child.mpesa_c2b_payment_register] = {
			"payment_entry": pe_name,
			"allocated": flt(child.allocated_amount),
			"excess": flt(child.amount) - flt(child.allocated_amount),
		}

	present_modes = {p.mode_of_payment for p in invoice.get("payments") or []}
	for mode in dict.fromkeys(c.mode_of_payment for c in children):
		if mode not in present_modes:
			invoice.append("payments", {"mode_of_payment": mode, "amount": 0})

	invoice.calculate_taxes_and_totals()
	invoice.save(ignore_permissions=True)
	return summary


@contextmanager
def _manual_reconciliation():
	"""Keep the register's on_submit from allocating these entries anywhere else.

	frappe_mpsa_payments' own quick-pay path sets this site global around a register
	submit for exactly the same reason (api/payment_entry.py); the register checks it at
	the top of on_submit. It is a global, not a request flag, so it is always released.

	Released to whatever it was, not to "0": running inside a caller that had already
	raised the guard - that quick-pay path does - would otherwise hand the register back
	its allocation powers halfway through the outer reconciliation.
	"""
	previous = frappe.db.get_global("is_manual_reconciliation")
	frappe.db.set_global("is_manual_reconciliation", "1")
	try:
		yield
	finally:
		frappe.db.set_global("is_manual_reconciliation", previous if previous is not None else "0")


def _finalize_mpesa_reconciliation(invoice, allocation_summary: dict | None = None) -> list[dict]:
	"""Post-submit phase: mark the receipts used and say where the money went.

	The invoice already took its share as advances (see _allocate_receipts_before_submit)
	and ERPNext reconciled them at submit. What is left is bookkeeping on the register:
	each row is submitted with submit_payment=0 (its entry already exists), pointing at
	its Payment Entry and at this invoice, so an accountant opening the register can
	follow the money in both directions.

	ERPNext skips that reconciliation for POS invoices, so this calls it here instead.

	`update_against_document_in_jv` is not idempotent - it appends a reference row to the
	entry on every call - so finalize must not be re-run on an invoice whose advances are
	already reconciled; a failure here rolls the whole submission back rather than leaving
	an invoice to be finalized a second time.

	Returns one row per receipt whose entry still holds unallocated money, in the shape
	PaymentDialog sums: excess_amount is the customer's credit from that receipt.
	"""
	if invoice.docstatus != 1:
		frappe.throw(
			_("Cannot finalize Mpesa reconciliation for {0}: invoice is not submitted (docstatus={1}).").format(
				invoice.name, invoice.docstatus
			)
		)

	# ERPNext reconciles an invoice's advance rows against their Payment Entries in
	# on_submit - except for POS invoices (sales_invoice.py: `if cint(self.is_pos) != 1`),
	# which it assumes carry no advances. Ours carry one per receipt, so do it here, or the
	# entries stay fully unallocated and the invoice reverts to its full outstanding.
	if invoice.get("advances"):
		invoice.update_against_document_in_jv()
		invoice.reload()

	results = []
	with _manual_reconciliation():
		for child in _pending_mpesa_rows(invoice):
			row = frappe.get_doc("Mpesa C2B Payment Register", child.mpesa_c2b_payment_register)
			row.customer = invoice.customer
			row.mode_of_payment = child.mode_of_payment
			if not row.company:
				row.company = invoice.company
			row.submit_payment = 0
			row.payment_entry = child.payment_entry
			if row.meta.has_field("sales_invoice"):
				row.sales_invoice = invoice.name
			row.save(ignore_permissions=True)
			row.submit()

	for child in invoice.get("custom_mpesa_reconciled_payments") or []:
		if not child.payment_entry:
			continue
		unallocated = flt(frappe.db.get_value("Payment Entry", child.payment_entry, "unallocated_amount"))
		if unallocated <= 0:
			continue
		# custom_mpesa_reconciled_payments is read-only on the submitted parent, so write
		# the child column directly.
		frappe.db.set_value(
			"POS Mpesa Reconciled Payment", child.name, "excess_payment_entry", child.payment_entry
		)
		results.append(
			{
				"mode_of_payment": child.mode_of_payment,
				"payment_entry": child.payment_entry,
				"register": child.mpesa_c2b_payment_register,
				"excess_amount": unallocated,
				"unallocated_amount": unallocated,
			}
		)

	invoice.reload()
	return results
