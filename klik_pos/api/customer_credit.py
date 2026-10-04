"""A customer's spendable credit, and spending it on an invoice.

Credit is an open credit note: a submitted Sales Invoice return whose outstanding is
negative. Spending it books the same "Credit Note" adjustment Journal Entry that desk
Payment Reconciliation books - ERPNext's own mechanism, nothing parallel to maintain.
"""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import flt


def _is_walkin_customer(customer):
	"""Lazy proxy to the sales_invoice helper - sales_invoice imports this module."""
	from klik_pos.api import sales_invoice

	return sales_invoice._is_walkin_customer(customer)


@frappe.whitelist()
def get_customer_credit(customer, company, currency=None):
	"""Open credit notes the customer can spend at this company's till.

	`currency` is the currency the till sells in; it defaults to the company's,
	and a caller holding a cart in another currency passes that one instead.
	"""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	if not customer or _is_walkin_customer(customer):
		return {"total": 0.0, "notes": []}
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	rows = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"company": company,
			"currency": currency,
			"docstatus": 1,
			"is_return": 1,
			"outstanding_amount": ["<", 0],
		},
		fields=["name", "posting_date", "outstanding_amount"],
		order_by="posting_date asc, name asc",
	)
	notes = [
		{
			"invoice": r.name,
			"posting_date": str(r.posting_date),
			"available": flt(-r.outstanding_amount, 2),
		}
		for r in rows
	]
	return {"total": flt(sum(n["available"] for n in notes), 2), "notes": notes}


def _same_number(typed, actual):
	"""A voucher number as a cashier types it: spaces and letter case do not matter."""
	if not isinstance(typed, str) or not isinstance(actual, str):
		return False
	return bool(actual) and typed.strip().upper() == actual.strip().upper()


@frappe.whitelist()
@rate_limit(limit=30, seconds=60)
def lookup_credit_voucher(credit_note, original_invoice):
	"""What a store-credit voucher holds: its credit note number plus the original sale's.

	A credit note is the voucher and its outstanding is the balance (negative = usable).
	Both numbers must match, and every failed lookup answers the same "no_match", so the
	lookup cannot be used to find out which credit notes exist.
	"""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	no_match = {"status": "no_match"}
	if not isinstance(credit_note, str) or not isinstance(original_invoice, str):
		return no_match
	credit_note = credit_note.strip()
	if not credit_note or not original_invoice.strip():
		return no_match

	meta = frappe.get_meta("Sales Invoice")
	walkin_fields = [f for f in ("custom_walkin_customer_name", "custom_walkin_phone") if meta.has_field(f)]
	note = frappe.db.get_value(
		"Sales Invoice",
		credit_note,
		[
			"name",
			"customer",
			"customer_name",
			"company",
			"currency",
			"docstatus",
			"is_return",
			"return_against",
			"grand_total",
			"rounded_total",
			"paid_amount",
			"outstanding_amount",
			*walkin_fields,
		],
		as_dict=True,
	)
	if not note or not note.is_return or note.docstatus == 0:
		return no_match
	if not _same_number(original_invoice, note.return_against):
		return no_match

	available = max(flt(-note.outstanding_amount, 2), 0.0) if note.docstatus == 1 else 0.0
	# What the voucher held when issued: the return's rounded total less the cash handed back
	# with it - the figure the return announced. It never reads below the balance left.
	issued = flt(abs(flt(note.rounded_total) or flt(note.grand_total)) - abs(flt(note.paid_amount)), 2)
	total = max(issued, available)
	if note.docstatus == 2:
		status = "cancelled"
	elif available <= 0:
		status = "used"
	elif available < total:
		status = "partly_used"
	else:
		status = "open"
	return {
		"status": status,
		"note": note.name,
		"original": note.return_against,
		"customer": note.customer,
		"customer_name": note.customer_name,
		"is_walkin": bool(_is_walkin_customer(note.customer)),
		"company": note.company,
		"currency": note.currency,
		"total": total,
		"available": available,
		"walkin_name": note.get("custom_walkin_customer_name"),
		"walkin_phone": note.get("custom_walkin_phone"),
	}


def validate_allocations(invoice_doc, allocations):
	"""Check every row BEFORE the sale submits, so apply cannot fail for business reasons."""
	normalized = []
	total = 0.0
	seen = set()
	for row in allocations or []:
		# Rows come from the till's payload: a dict "invoice" would be read as a filter and
		# pick a note by any field, so only plain text numbers are accepted.
		if not isinstance(row, dict) or not isinstance(row.get("invoice"), str):
			frappe.throw("A voucher row must name its credit note.")
		original = row.get("original")
		if original is not None and not isinstance(original, str):
			frappe.throw(f"{row['invoice']}: the original sale number must be text.")
		name, amount = row["invoice"], flt(row.get("amount"), 2)
		if amount <= 0:
			continue
		note = frappe.db.get_value(
			"Sales Invoice",
			name,
			[
				"name",
				"customer",
				"company",
				"currency",
				"docstatus",
				"is_return",
				"outstanding_amount",
				"return_against",
			],
			as_dict=True,
		)
		if not note or note.docstatus != 1 or not note.is_return:
			frappe.throw(f"{name} is not a submitted credit note.")
		if note.name in seen:
			frappe.throw(f"{note.name} is listed twice - apply each voucher once.")
		seen.add(note.name)
		if note.customer != invoice_doc.customer:
			frappe.throw(f"{name} belongs to another customer.")
		if note.company != invoice_doc.company or note.currency != invoice_doc.currency:
			frappe.throw(f"{name} is from another company or currency.")
		# Walk In credit belongs to whoever holds the receipt, so both of its numbers are
		# checked again here: a payload can never spend a Walk In note by its number alone.
		if _is_walkin_customer(note.customer) and not _same_number(row.get("original"), note.return_against):
			frappe.throw(f"{name} is a Walk In voucher - enter its original sale number to use it.")
		available = flt(-note.outstanding_amount, 2)
		if amount > available:
			frappe.throw(f"{name} holds {available}, not {amount}.")
		normalized.append({"invoice": note.name, "amount": amount})
		total += amount
	# The rounded total: the invoice's outstanding is built from it, and the till caps a
	# voucher at it - a total that rounds up would refuse a voucher paying exactly that.
	if total > flt(invoice_doc.rounded_total or invoice_doc.grand_total, 2):
		frappe.throw("Credit exceeds the invoice total.")
	return normalized


def apply_customer_credit(invoice_name, allocations):
	"""Reconcile each note against the submitted invoice - the desk tool's own path."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	before = {je.name for je in _adjustment_jes(invoice_name)}
	applied = 0.0
	for row in allocations:
		pr = frappe.new_doc("Payment Reconciliation")
		pr.company = invoice.company
		pr.party_type = "Customer"
		pr.party = invoice.customer
		pr.receivable_payable_account = invoice.debit_to
		# Name both sides so ERPNext filters server-side: without this, its 50-row
		# fetch caps can slice a busy customer's credit notes out of the list entirely.
		pr.payment_name = row["invoice"]
		pr.invoice_name = invoice_name
		pr.get_unreconciled_entries()
		payments = [p.as_dict() for p in pr.payments if p.reference_name == row["invoice"]]
		invoices = [i.as_dict() for i in pr.invoices if i.invoice_number == invoice_name]
		if not payments or not invoices:
			frappe.throw(f"{row['invoice']} no longer holds credit to apply.")
		pr.allocate_entries(frappe._dict({"payments": payments, "invoices": invoices}))
		for a in pr.allocation:
			a.allocated_amount = min(flt(a.allocated_amount, 2), flt(row["amount"], 2))
		pr.reconcile()
		# What actually got booked, not what was asked: a concurrently drained note
		# reconciles less, and the caller reports that honestly.
		applied += flt(sum(flt(a.allocated_amount) for a in pr.allocation), 2)
	return {
		"applied": flt(applied, 2),
		"journal_entries": [je.name for je in _adjustment_jes(invoice_name) if je.name not in before],
	}


def release_customer_credit(invoice_name):
	"""Cancel the adjustment JEs referencing the invoice; both outstandings restore."""
	cancelled = []
	for je in _adjustment_jes(invoice_name):
		frappe.get_doc("Journal Entry", je.name).cancel()
		cancelled.append(je.name)
	return cancelled


def _adjustment_jes(invoice_name):
	"""Submitted Credit Note adjustment JEs with a row referencing the invoice."""
	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"reference_type": "Sales Invoice", "reference_name": invoice_name, "docstatus": 1},
		fields=["parent"],
	)
	names = sorted({r.parent for r in rows})
	return [
		frappe._dict(name=n)
		for n in names
		if frappe.db.get_value("Journal Entry", n, ["voucher_type", "docstatus"]) == ("Credit Note", 1)
	]
