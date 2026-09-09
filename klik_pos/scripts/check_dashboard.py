"""Check the dashboard endpoint against a second, deliberately naive computation.

Run before turning DASHBOARD_V2_ENABLED on for a site. The endpoint answers in seven SQL
aggregations; this recomputes the same figures by loading the documents and adding them up
in Python, sharing no code with it, so an error in one is unlikely to be reproduced by the
other. Anything but zero differences is a reason not to flip the flag.

    bench --site <site> execute klik_pos.scripts.check_dashboard.compare \\
        --kwargs "{'company': 'Dev Co', 'date_from': '2026-09-01', 'date_to': '2026-09-06'}"

    bench --site <site> execute klik_pos.scripts.check_dashboard.compare_open_shifts \\
        --kwargs "{'company': 'Dev Co'}"

The shift form also checks every open shift's POS Closing Entry totals, which is the figure
the cashier reconciles cash against.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.dashboard import get_dashboard_summary
from klik_pos.api.pos_entry import _calculate_closing_entry_totals

TOLERANCE = 0.01


def compare(company=None, date_from=None, date_to=None, pos_profiles=None):
	"""Diff the endpoint against a hand computation over a date range."""
	summary = get_dashboard_summary(
		company=company,
		pos_profiles=pos_profiles,
		date_range="custom",
		date_from=date_from,
		date_to=date_to,
	)
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": summary["scope"]["company"],
			"pos_profile": ["in", summary["scope"]["pos_profiles"]],
			"docstatus": 1,
			"posting_date": ["between", [date_from, date_to]],
		},
		pluck="name",
	)
	return _report(summary, invoices)


def compare_open_shifts(company=None, pos_profiles=None):
	"""Diff the endpoint against a hand computation over whatever shifts are open."""
	summary = get_dashboard_summary(company=company, pos_profiles=pos_profiles, date_range="shift")
	entries = summary["scope"]["opening_entries"]
	if not entries:
		print("No shift is open; the endpoint fell back to today. Use compare() for a date range.")
		return None

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"custom_pos_opening_entry": ["in", entries], "docstatus": 1},
		pluck="name",
	)
	differences = _report(summary, invoices)

	print("\nPOS Closing Entry totals, per shift:")
	for entry in entries:
		totals = _calculate_closing_entry_totals(entry)
		naive = _naive_closing_totals(entry)
		for key in ("grand_total", "net_total", "total_quantity"):
			gap = flt(totals[key]) - flt(naive[key])
			flag = "OK  " if abs(gap) <= TOLERANCE else "DIFF"
			print(f"  {flag} {entry} {key}: {totals[key]} vs {naive[key]} (diff {round(gap, 4)})")
			if abs(gap) > TOLERANCE:
				differences.append(f"{entry}.{key}")

	print(f"\n{len(differences)} difference(s).")
	return differences


def _naive_closing_totals(opening_entry):
	"""One document at a time, counted once each - no joins to get wrong."""
	names = frappe.get_all(
		"Sales Invoice",
		filters={"custom_pos_opening_entry": opening_entry, "docstatus": 1},
		pluck="name",
	)
	totals = {"grand_total": 0.0, "net_total": 0.0, "total_quantity": 0.0}
	for name in names:
		doc = frappe.get_doc("Sales Invoice", name)
		totals["grand_total"] += flt(doc.grand_total)
		totals["net_total"] += flt(doc.net_total)
		totals["total_quantity"] += sum(flt(item.qty) for item in doc.items)
	return totals


def _report(summary, invoice_names):
	"""Recompute the identity from the documents themselves and print every difference."""
	billed = billed_gross = credit = refunds = write_off = 0.0
	at_sale: dict[str, float] = {}
	change = 0.0

	for name in invoice_names:
		doc = frappe.get_doc("Sales Invoice", name)
		payable = (
			flt(doc.base_rounded_total)
			if not doc.disable_rounded_total and flt(doc.base_rounded_total)
			else flt(doc.base_grand_total)
		)
		billed += payable
		billed_gross += flt(doc.base_grand_total)
		write_off += flt(doc.base_write_off_amount)
		change += flt(doc.base_change_amount)

		outstanding = flt(doc.outstanding_amount) * (flt(doc.conversion_rate) or 1)
		if outstanding > 0.001:
			credit += outstanding
		elif doc.is_return and outstanding < -0.001:
			refunds += -outstanding

		for payment in doc.get("payments") or []:
			if payment.mode_of_payment:
				at_sale[payment.mode_of_payment] = at_sale.get(
					payment.mode_of_payment, 0.0
				) + flt(payment.base_amount)

	later: dict[str, float] = {}
	references = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": ["in", invoice_names or [""]], "docstatus": 1},
		fields=["parent", "allocated_amount"],
	)
	for reference in references:
		entry = frappe.db.get_value(
			"Payment Entry",
			reference.parent,
			["mode_of_payment", "payment_type", "docstatus", "source_exchange_rate", "custom_pos_opening_entry"],
			as_dict=True,
		)
		if not entry or entry.docstatus != 1 or entry.payment_type != "Receive" or not entry.mode_of_payment:
			continue
		amount = flt(reference.allocated_amount) * (flt(entry.source_exchange_rate) or 1)
		if entry.custom_pos_opening_entry:
			at_sale[entry.mode_of_payment] = at_sale.get(entry.mode_of_payment, 0.0) + amount
		else:
			later[entry.mode_of_payment] = later.get(entry.mode_of_payment, 0.0) + amount

	# Change only ever leaves the drawer as cash, the same rule the endpoint applies.
	for mode in list(at_sale):
		if mode.strip().lower() == "cash":
			at_sale[mode] -= change

	identity = summary["identity"]
	rows = {row["mode"]: row for row in summary["collected_by_mode"]}
	differences = []

	def check(label, endpoint_value, naive_value):
		gap = flt(endpoint_value) - flt(naive_value)
		flag = "OK  " if abs(gap) <= TOLERANCE else "DIFF"
		print(f"  {flag} {label}: {round(flt(endpoint_value), 2)} vs {round(flt(naive_value), 2)} (diff {round(gap, 4)})")
		if abs(gap) > TOLERANCE:
			differences.append(label)

	print(f"Scope: {summary['scope']['range']} · {len(invoice_names)} invoices · {summary['scope']['pos_profiles']}")
	print("Identity:")
	check("billed", identity["billed"], billed)
	check("billed_gross", identity["billed_gross"], billed_gross)
	check("collected_at_sale", identity["collected_at_sale"], sum(at_sale.values()))
	check("collected_later", identity["collected_later"], sum(later.values()))
	check("credit", identity["credit"], credit)
	check("refunds_owed", identity["refunds_owed"], refunds)
	check("write_off", identity["write_off"], write_off)
	check("unexplained (must be 0)", identity["unexplained"], 0)

	print("By mode:")
	for mode in sorted(set(at_sale) | set(later) | set(rows)):
		check(f"{mode} at sale", rows.get(mode, {}).get("amount", 0), at_sale.get(mode, 0))
		check(f"{mode} later", rows.get(mode, {}).get("later", 0), later.get(mode, 0))

	print(f"\n{len(differences)} difference(s) so far.")
	return differences
