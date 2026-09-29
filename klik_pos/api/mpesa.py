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
from frappe.utils import cint, flt


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


_UNUSABLE = "unusable"


def _klik_entry_for_transid(transid: str | None) -> str | None:
	"""The submitted Payment Entry klik already minted for this receipt, found by the
	receipt number it is stamped with. Covers entries minted before the register row was
	linked at mint time (a checkout that failed after minting)."""
	if not transid or not frappe.db.has_column("Payment Entry", "custom_mpesa_receipt_number"):
		return None
	return frappe.db.get_value(
		"Payment Entry", {"custom_mpesa_receipt_number": transid, "docstatus": 1}, "name"
	)


def _receipt_balance(register: str) -> frappe._dict:
	"""What one M-Pesa receipt can still pay, and for whom.

	A receipt that has a submitted Payment Entry is that entry: `open` while the entry has
	unallocated money, `spent` once it has none, and held by the entry's customer. A receipt
	with no entry yet is `new` for its whole amount, for any customer. Anything else - a
	cancelled row, a cancelled or draft entry, a supplier entry, another company - is
	`unusable`. The register row's own docstatus says only whether it has been consumed
	once, not whether money is left.
	"""
	row = frappe.db.get_value(
		"Mpesa C2B Payment Register",
		register,
		["name", "docstatus", "transamount", "transid", "company", "payment_entry"],
		as_dict=True,
	)
	out = frappe._dict(state=_UNUSABLE, open_amount=0.0, payment_entry=None, held_by=None, transid=None)
	if not row:
		return out
	out.transid = row.transid
	if row.docstatus == 2:
		return out

	pe_name = row.payment_entry or _klik_entry_for_transid(row.transid)
	if pe_name:
		pe = frappe.db.get_value(
			"Payment Entry",
			pe_name,
			["docstatus", "party_type", "party", "unallocated_amount", "company"],
			as_dict=True,
		)
		out.payment_entry = pe_name
		if not pe or pe.docstatus != 1 or pe.party_type != "Customer" or (row.company and pe.company != row.company):
			return out
		out.held_by = pe.party
		out.open_amount = flt(pe.unallocated_amount)
		out.state = "open" if out.open_amount > 0 else "spent"
		return out

	if row.docstatus == 0 and flt(row.transamount) > 0:
		out.state = "new"
		out.open_amount = flt(row.transamount)
	return out


def _stk_used_transids(transids: list[str]) -> set[str]:
	"""Receipt numbers that already paid a live sale through a completed STK push. The same
	money often lands in the register as a C2B row too; offering that row again would let
	one payment pay twice."""
	if not transids:
		return set()
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT req.transaction_id
		FROM `tabMpesa Express Request` req
		INNER JOIN `tabSales Invoice Payment` sip ON sip.custom_reference_text = req.name
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE req.status = 'Completed' AND req.transaction_id IN %(ids)s AND si.docstatus = 1
		""",
		{"ids": tuple(transids)},
	)
	return {r[0] for r in rows}



def _mpesa_modes() -> set[str]:
	"""Modes whose money is M-Pesa: Phone-type Modes of Payment, and whatever a register URL
	maps a shortcode to. A bank's own M-Pesa collection mode (Bank type) is not one."""
	cached = getattr(frappe.local, "_klik_mpesa_modes", None)
	if cached is None:
		cached = set(frappe.get_all("Mode of Payment", filters={"type": "Phone"}, pluck="name"))
		cached |= {m for m in frappe.get_all("Mpesa C2B Payment Register URL", pluck="mode_of_payment") if m}
		# ERPNext's M-Pesa integration names the mode it creates after the settings record.
		settings_modes = [f"Mpesa-{name}" for name in frappe.get_all("Mpesa Settings", pluck="name")]
		cached |= set(frappe.get_all("Mode of Payment", filters={"name": ["in", settings_modes]}, pluck="name"))
		frappe.local._klik_mpesa_modes = cached
	return cached


def is_mpesa_mode(mode: str | None) -> bool:
	return bool(mode) and mode in _mpesa_modes()


def _stk_backs(payment_row, invoice_name: str) -> bool:
	"""A completed STK push for at least this row's amount, not already used on another sale.

	klik names the request in `custom_reference_text`; the desk's own STK flow puts the
	request's M-Pesa transaction id in `reference_no` instead. Either identifies it.
	"""
	refs = {r for r in (payment_row.get("custom_reference_text"), payment_row.get("reference_no")) if r}
	if not refs:
		return False
	req = frappe.db.get_value(
		"Mpesa Express Request",
		{"name": ["in", list(refs)]},
		["name", "status", "transaction_id", "amount"],
		as_dict=True,
	) or frappe.db.get_value(
		"Mpesa Express Request",
		{"transaction_id": ["in", list(refs)], "status": "Completed"},
		["name", "status", "transaction_id", "amount"],
		as_dict=True,
	)
	if not req or req.status != "Completed" or not req.transaction_id or flt(req.amount) < flt(payment_row.amount):
		return False
	used_elsewhere = frappe.db.sql(
		"""SELECT 1 FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE (sip.custom_reference_text IN %(ids)s OR sip.reference_no IN %(ids)s)
			AND si.name != %(invoice)s AND si.docstatus = 1 LIMIT 1""",
		{"ids": (req.name, req.transaction_id), "invoice": invoice_name},
	)
	return not used_elsewhere


def _register_backs(payment_row) -> bool:
	"""The M-Pesa app's own quick-pay names the register receipt it consumed on the row."""
	refs = [r for r in (payment_row.get("custom_reference_text"), payment_row.get("reference_no")) if r]
	if not refs:
		return False
	return bool(
		frappe.db.exists("Mpesa C2B Payment Register", {"name": ["in", refs], "docstatus": ["<", 2]})
		or frappe.db.exists("Mpesa C2B Payment Register", {"transid": ["in", refs], "docstatus": ["<", 2]})
	)


def assert_mpesa_rows_backed(invoice) -> None:
	"""Refuse M-Pesa money that no receipt stands behind.

	Receipt-paid M-Pesa reaches a sale as an advance from the receipt's Payment Entry and
	leaves only a zero placeholder row here; an amount typed straight into an M-Pesa row
	posts to the M-Pesa account on its own, and when the real receipt is later reconciled
	the same money is counted twice. So a positive M-Pesa payment row passes only when it is
	a completed STK push not already used on another sale, or names a register receipt the
	M-Pesa app's quick-pay consumed. Returns are refunds and exempt.
	"""
	# A consolidated invoice is ERPNext merging POS Invoices at closing; its rows are sums
	# of rows each checked on their own invoice.
	if not cint(invoice.get("is_pos")) or cint(invoice.get("is_return")) or cint(invoice.get("is_consolidated")):
		return
	unbacked = [
		p
		for p in invoice.get("payments") or []
		if is_mpesa_mode(p.mode_of_payment)
		and flt(p.amount) > 0
		and not _stk_backs(p, invoice.name)
		and not _register_backs(p)
	]
	if unbacked:
		frappe.throw(
			"<br>".join(
				_(
					"{0} shows {1} with no M-Pesa receipt behind it. Pick the receipt from M-Pesa options, or send an STK push."
				).format(p.mode_of_payment, frappe.format_value(p.amount, {"fieldtype": "Currency"}))
				for p in unbacked
			),
			title=_("M-Pesa not received"),
		)

@frappe.whitelist()
def get_mpesa_payments(
	company: str,
	pos_profile: str | None = None,
	mode_of_payment: str | None = None,
	search: str | None = None,
	customer: str | None = None,
) -> dict:
	"""Receipts with money left for `company`: untouched register rows at their full
	amount, and rows already used once whose Payment Entry still has unallocated money, at
	that amount. `customer` does not filter - another customer's receipt is still listed so
	the cashier can see it, with `selectable` false (a leftover can pay only the customer
	its entry belongs to). A 3+ character `search` returns rows; without one only the count.

	`mode_of_payment` is accepted for query-string compatibility and not used to filter: a
	pending row's mode is only filled in later (see set_missing_values), so filtering on it
	would drop every unassigned row.
	"""
	shortcodes = _mpesa_shortcodes_for_company(company)
	if not shortcodes:
		return {"count": 0, "payments": [], "shortcodes": []}

	has_money_left = """
		reg.businessshortcode IN %(codes)s
		AND reg.docstatus < 2
		AND (
			(reg.docstatus = 0 AND IFNULL(reg.payment_entry, '') = '' AND reg.transamount > 0)
			OR (pe.docstatus = 1 AND pe.unallocated_amount > 0)
		)
	"""
	params = {"codes": tuple(shortcodes)}
	total_count = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabMpesa C2B Payment Register` reg
		LEFT JOIN `tabPayment Entry` pe ON pe.name = reg.payment_entry
		WHERE {has_money_left}""",
		params,
	)[0][0]

	payments = []
	search = (search or "").strip()
	if len(search) >= 3:
		params["s"] = f"%{search}%"
		rows = frappe.db.sql(
			f"""
			SELECT reg.name, reg.full_name, reg.transamount, reg.transid, reg.msisdn,
				reg.posting_date, reg.billrefnumber, reg.businessshortcode, reg.creation
			FROM `tabMpesa C2B Payment Register` reg
			LEFT JOIN `tabPayment Entry` pe ON pe.name = reg.payment_entry
			WHERE {has_money_left}
				AND (reg.full_name LIKE %(s)s OR reg.transid LIKE %(s)s
					OR reg.billrefnumber LIKE %(s)s OR reg.msisdn LIKE %(s)s)
			ORDER BY reg.creation DESC
			LIMIT 100
			""",
			params,
			as_dict=True,
		)
		stk_used = _stk_used_transids([r.transid for r in rows if r.transid])
		for r in rows:
			if r.transid in stk_used:
				continue
			bal = _receipt_balance(r.name)
			if bal.state not in ("new", "open"):
				continue
			used_count = (
				frappe.db.count(
					"Payment Entry Reference",
					{
						"parent": bal.payment_entry,
						"reference_doctype": "Sales Invoice",
						"allocated_amount": [">", 0],
					},
				)
				if bal.payment_entry
				else 0
			)
			payments.append(
				{
					**r,
					"state": bal.state,
					"open_amount": bal.open_amount,
					"payment_entry": bal.payment_entry,
					"held_by": bal.held_by,
					"used_count": used_count,
					"selectable": not bal.held_by or not customer or bal.held_by == customer,
				}
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

	on_invoice = {c.mpesa_c2b_payment_register for c in invoice.get("custom_mpesa_reconciled_payments") or []}
	picked = []
	invalid = []
	for name in names:
		if not frappe.db.exists("Mpesa C2B Payment Register", name):
			invalid.append(_("{0} (not found)").format(name))
			continue
		bal = _receipt_balance(name)
		label = bal.transid or name
		if name in on_invoice:
			invalid.append(_("{0} (already on this invoice)").format(label))
		elif bal.state == "spent":
			invalid.append(_("{0} (nothing left on it)").format(label))
		elif bal.state not in ("new", "open"):
			invalid.append(
				_("{0} (cannot be used: cancelled, or its Payment Entry is not a submitted customer receipt)").format(
					label
				)
			)
		elif bal.held_by and bal.held_by != invoice.customer:
			invalid.append(
				_("{0} (held by {1}; switch the sale to that customer to use it)").format(label, bal.held_by)
			)
		else:
			picked.append((frappe.get_doc("Mpesa C2B Payment Register", name), bal))

	if invalid:
		frappe.throw(_("Cannot use these M-Pesa receipts: {0}").format("; ".join(invalid)))

	total_amount = sum(flt(bal.open_amount) for _row, bal in picked)

	payments_added = [
		{"mode_of_payment": mode_of_payment, "amount": bal.open_amount, "reference": row.transid}
		for row, bal in picked
	]

	# Traceability only: a new receipt's register row stays a draft until the invoice is
	# submitted (see `_finalize_mpesa_reconciliation`); an open one already names its entry.
	for row, bal in picked:
		invoice.append(
			"custom_mpesa_reconciled_payments",
			{
				"mpesa_c2b_payment_register": row.name,
				"transid": row.transid,
				"amount": bal.open_amount,
				"msisdn": row.msisdn,
				"mode_of_payment": mode_of_payment,
				"payment_entry": bal.payment_entry,
			},
		)

	invoice.save()

	result = {
		"success": True,
		"payments_added": payments_added,
		"mpesa_payments": [{"name": row.name, "amount": bal.open_amount} for row, bal in picked],
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


def _refuse_if_used_meanwhile(doctype: str, name: str, field: str, current, transid: str | None):
	"""Refuse when another till changed this receipt after our transaction began.

	The row lock (`FOR UPDATE`) returns the row as it is now, but MariaDB's repeatable-read
	snapshot keeps showing every other read in this transaction the row as it was when the
	transaction started. ERPNext's reconciliation reads the Payment Entry that way, so going
	on would either trip its "modified after you pulled it" check or, worse, write the entry
	back from stale figures and undo the other till's allocation. A resubmit runs in a fresh
	transaction and sees the receipt as it now stands.
	"""
	snapshot = frappe.db.sql(f"SELECT `{field}` FROM `tab{doctype}` WHERE name=%s", name)
	was = snapshot[0][0] if snapshot else None
	same = (flt(was) == flt(current)) if field == "unallocated_amount" else ((was or None) == (current or None))
	if not same or not snapshot:
		frappe.throw(
			_("{0} was used on another sale a moment ago. Submit again to use what is left on it.").format(
				transid or name
			),
			title=_("Receipt just used"),
		)


def _usable_mpesa_rows(invoice) -> list:
	"""Recorded trace rows whose receipt can still pay: new (no entry yet) or open (its
	entry has money left). Minting and allocation go by this; finalise still consumes only
	the draft register rows (`_pending_mpesa_rows`)."""
	return [
		child
		for child in invoice.get("custom_mpesa_reconciled_payments") or []
		if _receipt_balance(child.mpesa_c2b_payment_register).state in ("new", "open")
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

	Only receipts that can still pay are minted or reused, the same filter the caller
	allocates by: a trace row whose receipt was spent elsewhere is stale.
	"""
	from frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry import create_payment_entry

	by_register = {}
	for child in _usable_mpesa_rows(invoice):
		register = child.mpesa_c2b_payment_register
		# Lock the register row: two tills picking the same new receipt must end up on one
		# entry, so the second waits here and then finds the entry the first linked.
		locked = frappe.db.sql(
			"SELECT payment_entry FROM `tabMpesa C2B Payment Register` WHERE name=%s FOR UPDATE", register
		)
		linked = locked[0][0] if locked else None
		_refuse_if_used_meanwhile("Mpesa C2B Payment Register", register, "payment_entry", linked, child.transid)
		existing = linked or child.payment_entry or _klik_entry_for_transid(child.transid)
		if existing and frappe.db.get_value("Payment Entry", existing, "docstatus") == 1:
			child.payment_entry = existing
			if not linked:
				frappe.db.set_value(
					"Mpesa C2B Payment Register", register, "payment_entry", existing, update_modified=False
				)
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
		# Linked now, not at finalise: the register row is how the next till finds this entry.
		frappe.db.set_value("Mpesa C2B Payment Register", register, "payment_entry", pe.name, update_modified=False)
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

	children = _usable_mpesa_rows(invoice)
	if not children:
		return empty

	_assert_cancellation_releases_payments()

	balances = {c.name: _receipt_balance(c.mpesa_c2b_payment_register) for c in children}

	# A retry re-enters with the advances of an earlier attempt still on the draft. They
	# recorded what each receipt held then; another till may have drawn on it since, and a
	# stale advance fails ERPNext's reconciliation after the invoice is already submitted.
	# So the receipts' advances are rebuilt from the locked balances every time.
	receipt_entries = {b.payment_entry for b in balances.values() if b.payment_entry}
	receipt_entries |= {c.payment_entry for c in children if c.payment_entry}
	invoice.set(
		"advances",
		[a for a in invoice.get("advances") or [] if a.reference_name not in receipt_entries],
	)

	payable = flt(invoice.rounded_total) or flt(invoice.grand_total)
	already_paid = sum(flt(p.amount) for p in invoice.get("payments") or [])
	already_advanced = sum(flt(a.allocated_amount) for a in invoice.get("advances") or [])
	remaining = max(payable - already_paid - already_advanced, 0.0)

	# A receipt the sale turns out not to need - the cashier took cash instead, or picked
	# one receipt too many - is let go before anything is minted: an entry for it would
	# consume the receipt and tie it to this customer for money this sale never took.
	planned = remaining
	for child in list(children):
		share = min(flt(balances[child.name].open_amount), planned)
		planned -= share
		if share <= 0:
			invoice.remove(child)
			children.remove(child)
	if not children:
		invoice.save(ignore_permissions=True)
		return empty

	by_register = _ensure_receipt_payment_entries(invoice)

	summary = {"received_total": 0.0, "allocated_total": 0.0, "by_register": {}}
	for child in children:
		pe_name = by_register[child.mpesa_c2b_payment_register]
		# Lock the entry and read what is left under the lock: another till drawing on the
		# same receipt waits here until this sale commits, then sees the reduced balance.
		pe_row = frappe.db.sql(
			"""SELECT unallocated_amount, party, source_exchange_rate, remarks
			FROM `tabPayment Entry` WHERE name=%s FOR UPDATE""",
			pe_name,
			as_dict=True,
		)[0]
		if pe_row.party != invoice.customer:
			frappe.throw(
				_("{0} is held by {1}; switch the sale to that customer to use it.").format(
					child.transid, pe_row.party
				)
			)
		available = flt(pe_row.unallocated_amount)
		_refuse_if_used_meanwhile("Payment Entry", pe_name, "unallocated_amount", available, child.transid)
		if available < flt(child.amount) and remaining > available:
			last = frappe.db.get_value(
				"Payment Entry Reference",
				{"parent": pe_name, "reference_doctype": "Sales Invoice"},
				"reference_name",
				order_by="creation desc",
			)
			frappe.throw(
				_(
					"{0} has only {1} left now; it was used on {2} a moment ago. Pick another receipt or take the rest another way."
				).format(
					child.transid,
					frappe.format_value(available, {"fieldtype": "Currency"}),
					last or _("another sale"),
				)
			)
		take = min(available, remaining) if remaining > 0 else 0.0
		if take > 0:
			invoice.append(
				"advances",
				{
					"reference_type": "Payment Entry",
					"reference_name": pe_name,
					"reference_row": None,
					"advance_amount": available,
					"allocated_amount": take,
					"ref_exchange_rate": flt(pe_row.source_exchange_rate) or 1,
					"remarks": pe_row.remarks,
				},
			)
			remaining -= take
		child.allocated_amount = take
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
