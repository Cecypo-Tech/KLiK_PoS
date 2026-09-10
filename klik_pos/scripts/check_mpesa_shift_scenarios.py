"""Five M-Pesa payment situations on one fresh shift, and the closing figures they produce.

    bench --site <site> execute klik_pos.scripts.check_mpesa_shift_scenarios.main

Opens a real POS Opening Entry on its own profile and cashier (so no shift already open on
this site is disturbed), sells five ways, then reconciles:

  1. part cash, part M-Pesa
  2. one M-Pesa receipt for the whole sale
  3. several receipts adding up to the sale exactly
  4. several receipts adding up to more than the sale
  5. one receipt for more than the sale

Change is only ever cash. M-Pesa is never paid back out, so an overpaid receipt keeps its
excess as unallocated credit on its own Payment Entry rather than opening the drawer.

Pass cleanup=0 to keep the shift and its documents for inspection.
"""

import json

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import process_mpesa
from klik_pos.api.pos_entry import (
	_calculate_closing_entry_totals,
	_calculate_payment_reconciliation,
	_create_and_submit_closing_doc,
)
from klik_pos.api.sales_invoice import _set_pos_opening_entry, submit_draft_invoice
from klik_pos.tests.mpesa_fixtures import make_c2b_payment

COMPANY = "Dev Co"
CUSTOMER = "Walk In"
ITEM = "Consulting"
MPESA = "Mpesa-111222"
SHORTCODE = "600978"
CASH = "Cash"
PROFILE = "QA Shift Scenarios"
CASHIER = "qa-shift-scenarios@example.com"
OPENING_CASH = 1000.0


def _ensure_cashier():
	if not frappe.db.exists("User", CASHIER):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": CASHIER,
				"first_name": "QA Shift",
				"last_name": "Scenarios",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", CASHIER)
	for role in ("Accounts Manager", "Accounts User", "Sales Manager", "Sales User", "Stock User"):
		if not user.get("roles", {"role": role}):
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return CASHIER


def _ensure_profile():
	if frappe.db.exists("POS Profile", PROFILE):
		return PROFILE
	source = frappe.get_doc("POS Profile", "_Test POS Profile")
	profile = frappe.copy_doc(source)
	profile.name = PROFILE
	profile.company = COMPANY
	profile.set("payments", [])
	profile.append("payments", {"mode_of_payment": CASH, "default": 1})
	profile.append("payments", {"mode_of_payment": MPESA, "default": 0})
	profile.set("applicable_for_users", [])
	profile.append("applicable_for_users", {"user": CASHIER, "default": 1})
	profile.insert(ignore_permissions=True)
	return profile.name


def _open_shift():
	existing = frappe.db.exists(
		"POS Opening Entry", {"pos_profile": PROFILE, "user": CASHIER, "status": "Open", "docstatus": 1}
	)
	if existing:
		# A previous run left this shift open (cleanup=0, or it stopped early). Reuse it
		# rather than fail: ERPNext allows one open shift per profile and per cashier.
		return frappe.get_doc("POS Opening Entry", existing)

	doc = frappe.new_doc("POS Opening Entry")
	doc.update(
		{
			"user": CASHIER,
			"company": COMPANY,
			"pos_profile": PROFILE,
			"posting_date": frappe.utils.nowdate(),
			"set_posting_time": 1,
			"period_start_date": frappe.utils.now_datetime(),
		}
	)
	# The till insists on an explanation when the float does not match the last closing,
	# which for a script that re-runs on the same profile is every time after the first.
	doc.append(
		"balance_details",
		{
			"mode_of_payment": CASH,
			"opening_amount": OPENING_CASH,
			"custom_variance_reason": "QA scenario run: float reset to a known figure",
		},
	)
	doc.append("balance_details", {"mode_of_payment": MPESA, "opening_amount": 0})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _receipt(amount, label):
	return make_c2b_payment(
		company=COMPANY,
		shortcode=SHORTCODE,
		amount=amount,
		msisdn="254700111222",
		billrefnumber=f"SHIFTQA-{label}",
	).name


def _sell(label, total, receipts, cash=0.0):
	si = frappe.new_doc("Sales Invoice")
	si.update({"customer": CUSTOMER, "company": COMPANY, "is_pos": 1, "pos_profile": PROFILE})
	si.append("items", {"item_code": ITEM, "qty": 1, "rate": total})
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	for row in si.get("payments") or []:
		row.amount = flt(cash) if row.mode_of_payment == CASH else 0
	# What the checkout path does with every sale: attach it to the cashier's open shift.
	_set_pos_opening_entry(si)
	si.insert(ignore_permissions=True)

	if receipts:
		process_mpesa(
			doctype="Sales Invoice",
			invoice_name=si.name,
			customer=CUSTOMER,
			mpesa_payments=",".join(receipts),
			mode_of_payment=MPESA,
			auto_save=1,
			auto_submit=0,
		)
	submit_draft_invoice(si.name)
	si.reload()

	entries = [c.payment_entry for c in si.get("custom_mpesa_reconciled_payments") or []]
	return {
		"scenario": label,
		"invoice": si.name,
		"sale": flt(si.rounded_total) or flt(si.grand_total),
		"shift": si.custom_pos_opening_entry,
		"cash_row": sum(flt(p.amount) for p in si.payments if p.mode_of_payment == CASH),
		"mpesa_received": sum(flt(frappe.db.get_value("Payment Entry", e, "paid_amount")) for e in entries),
		"allocated": flt(si.total_advance),
		"unallocated": sum(
			flt(frappe.db.get_value("Payment Entry", e, "unallocated_amount")) for e in entries
		),
		"outstanding": flt(si.outstanding_amount),
		"change": flt(si.change_amount),
	}


def main(cleanup=1):
	try:
		_run(cleanup)
	except Exception:
		# `bench execute` swallows whatever a command raises and reports a NameError on the
		# module instead, which hides every real failure in here.
		import traceback

		traceback.print_exc()
		raise


def _run(cleanup):
	_ensure_cashier()
	_ensure_profile()
	frappe.set_user(CASHIER)
	shift = _open_shift()
	print(f"shift {shift.name} on {PROFILE} for {CASHIER}: opening cash {OPENING_CASH}, opening M-Pesa 0\n")

	results = [
		_sell("1. part cash, part M-Pesa", 1000, [_receipt(600, "s1")], cash=400),
		_sell("2. one receipt, exact", 500, [_receipt(500, "s2")]),
		_sell(
			"3. three receipts, exact",
			900,
			[_receipt(300, "s3a"), _receipt(400, "s3b"), _receipt(200, "s3c")],
		),
		_sell("4. two receipts, over", 700, [_receipt(400, "s4a"), _receipt(500, "s4b")]),
		_sell("5. one receipt, over", 300, [_receipt(500, "s5")]),
	]
	frappe.db.commit()

	sold = sum(r["sale"] for r in results)
	cash_taken = sum(r["cash_row"] for r in results)
	mpesa_taken = sum(r["mpesa_received"] for r in results)
	credit = sum(r["unallocated"] for r in results)

	print(
		f"{'scenario':28} {'sale':>8} {'cash':>8} {'mpesa in':>9} {'applied':>8} {'credit':>7} {'due':>5} {'change':>7}"
	)
	for r in results:
		print(
			f"{r['scenario']:28} {r['sale']:8.0f} {r['cash_row']:8.0f} {r['mpesa_received']:9.0f} "
			f"{r['allocated']:8.0f} {r['unallocated']:7.0f} {r['outstanding']:5.0f} {r['change']:7.0f}"
		)
	print(f"{'TOTAL':28} {sold:8.0f} {cash_taken:8.0f} {mpesa_taken:9.0f} {'':8} {credit:7.0f}\n")

	counted = {CASH: OPENING_CASH + cash_taken, MPESA: mpesa_taken}
	rows = _calculate_payment_reconciliation(shift, {"closing_balance": counted})
	print(f"{'mode':22} {'opening':>9} {'expected':>9} {'counted':>9} {'difference':>11}")
	for row in sorted(rows, key=lambda r: r["mode_of_payment"]):
		print(
			f"{row['mode_of_payment']:22} {flt(row['opening_amount']):9.0f} {flt(row['expected_amount']):9.0f} "
			f"{flt(row['closing_amount']):9.0f} {flt(row['difference']):11.0f}"
		)

	totals = _calculate_closing_entry_totals(shift.name)
	print(f"\nshift sales total: {flt(totals.get('grand_total')):.0f}")

	from klik_pos.overrides.pos_closing_entry import get_invoices

	desk = get_invoices(
		start=shift.period_start_date, end=frappe.utils.now_datetime(), pos_profile=PROFILE, user=CASHIER
	)["payments"]
	print("desk form sees:", json.dumps({p["mode_of_payment"]: flt(p["amount"]) for p in desk}))

	# The document itself, through the same call the Close Shift button makes.
	closing = _create_and_submit_closing_doc(shift, {"closing_balance": counted, "taxes": []}, rows, CASHIER)
	frappe.db.commit()
	stored = frappe.get_doc("POS Closing Entry", closing.name if hasattr(closing, "name") else closing)
	print(f"\nclosing entry {stored.name}: grand total {flt(stored.grand_total):.0f}")
	for row in sorted(stored.payment_reconciliation, key=lambda r: r.mode_of_payment):
		print(
			f"  {row.mode_of_payment:22} expected {flt(row.expected_amount):8.0f} "
			f"counted {flt(row.closing_amount):8.0f} difference {flt(row.difference):6.0f}"
		)

	by_mode = {r["mode_of_payment"]: r for r in rows}
	assert sum(r["outstanding"] for r in results) == 0, "every sale settled"
	assert all(r["change"] == 0 for r in results), "M-Pesa never opened the drawer"
	assert credit == 400, f"the two overpayments left 400 as credit, got {credit}"
	assert flt(by_mode[CASH]["expected_amount"]) == OPENING_CASH + cash_taken, (
		"cash expected = opening + till"
	)
	assert flt(by_mode[MPESA]["expected_amount"]) == mpesa_taken, "M-Pesa expected = every shilling received"
	assert all(flt(r["difference"]) == 0 for r in rows), "a correct count reconciles to zero"
	assert flt(totals.get("grand_total")) == sold, "the shift's sales total matches what was sold"
	assert flt(stored.grand_total) == sold, "and so does the closing entry that was filed"
	assert all(flt(r.difference) == 0 for r in stored.payment_reconciliation), "filed with no variance"
	print("\nALL SCENARIOS RECONCILE")

	frappe.set_user("Administrator")
	if int(cleanup):
		reset()


def reset():
	"""Undo everything this script has ever posted on its profile, so a run starts clean."""
	try:
		_reset()
	except Exception:
		import traceback

		traceback.print_exc()
		raise


def _reset():
	frappe.set_user("Administrator")
	# A closing entry refuses to cancel while any shift on its profile is open, so the
	# shifts are stood down first.
	for shift in frappe.get_all(
		"POS Opening Entry", filters={"pos_profile": PROFILE, "status": "Open"}, pluck="name"
	):
		frappe.db.set_value("POS Opening Entry", shift, "status", "Closed", update_modified=False)
	# The closing entry owns the shift it filed, so it goes before anything it counted.
	for closing in frappe.get_all(
		"POS Closing Entry", filters={"pos_profile": PROFILE, "docstatus": 1}, pluck="name"
	):
		frappe.get_doc("POS Closing Entry", closing).cancel()
	invoices = frappe.get_all("Sales Invoice", filters={"pos_profile": PROFILE, "docstatus": 1}, pluck="name")
	# Order matters both ways round: the register row refuses to cancel while its invoice
	# is live, and the Payment Entry refuses while the register row still links it.
	for name in invoices:
		si = frappe.get_doc("Sales Invoice", name)
		rows = [
			(c.mpesa_c2b_payment_register, c.payment_entry)
			for c in si.get("custom_mpesa_reconciled_payments") or []
		]
		si.cancel()
		for register, entry in rows:
			if register and frappe.db.get_value("Mpesa C2B Payment Register", register, "docstatus") == 1:
				frappe.get_doc("Mpesa C2B Payment Register", register).cancel()
			if entry and frappe.db.get_value("Payment Entry", entry, "docstatus") == 1:
				frappe.get_doc("Payment Entry", entry).cancel()
	for row in frappe.get_all(
		"Mpesa C2B Payment Register", filters={"billrefnumber": ["like", "SHIFTQA-%"]}, pluck="name"
	):
		doc = frappe.get_doc("Mpesa C2B Payment Register", row)
		if doc.docstatus == 1:
			doc.cancel()
		doc.delete(ignore_permissions=True)
	frappe.db.commit()
	print(f"reset: {len(invoices)} invoice(s) cancelled, receipts removed, shift(s) closed")
