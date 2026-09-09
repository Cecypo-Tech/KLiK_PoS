"""Run the three QA260906 scenarios through the real endpoints and print what posted.

    bench --site <site> execute klik_pos.scripts.check_mpesa_pe_first.main

Seeds a fresh batch, sells 600/500/200 against split/straddle/overpay receipts exactly as
the manual QA note describes, then prints per invoice: payment rows, advances, the GL on
the M-Pesa account, each register row's links, and each entry's unallocated balance. Ends
by asserting the three properties this work exists for, and cleans the batch up.
"""

import json

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import process_mpesa
from klik_pos.api.sales_invoice import submit_draft_invoice
from klik_pos.tests.mpesa_fixtures import cleanup_qa_batch, seed_qa_batch

COMPANY = "Dev Co"
PROFILE = "_Test POS Profile"
CUSTOMER = "Walk In"
ITEM = "Consulting"
MODE = "Mpesa-111222"


def _draft(total):
	si = frappe.new_doc("Sales Invoice")
	si.update({"customer": CUSTOMER, "company": COMPANY, "is_pos": 1, "pos_profile": PROFILE, "set_posting_time": 1, "posting_time": "11:00:00"})
	si.append("items", {"item_code": ITEM, "qty": 1, "rate": total})
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	for p in si.get("payments") or []:
		p.amount = 0
	si.insert(ignore_permissions=True)
	return si


def _sell(label, total, registers):
	si = _draft(total)
	process_mpesa(doctype="Sales Invoice", invoice_name=si.name, customer=CUSTOMER,
		mpesa_payments=",".join(registers), mode_of_payment=MODE, auto_save=1, auto_submit=0)
	submit_draft_invoice(si.name)
	si.reload()
	entries = [c.payment_entry for c in si.custom_mpesa_reconciled_payments]
	return {
		"scenario": label, "invoice": si.name, "outstanding": flt(si.outstanding_amount),
		"total_advance": flt(si.total_advance), "change_amount": flt(si.change_amount),
		"payment_rows": [(p.mode_of_payment, flt(p.amount)) for p in si.payments],
		"advances": [(a.reference_name, flt(a.allocated_amount), flt(a.advance_amount)) for a in si.advances],
		"entries": [(e, flt(frappe.db.get_value("Payment Entry", e, "unallocated_amount"))) for e in entries],
		"registers": [frappe.db.get_value("Mpesa C2B Payment Register", r, ["name", "docstatus", "payment_entry", "sales_invoice"], as_dict=True) for r in registers],
		"mpesa_gl": frappe.db.sql("select voucher_no, debit, credit from `tabGL Entry` where voucher_no in %(v)s and account like 'Mpesa%%' and is_cancelled=0", {"v": tuple(entries + [si.name])}, as_dict=True),
	}


def main():
	label = f"QAPE{frappe.utils.now_datetime().strftime('%H%M%S')}"
	seed_qa_batch(company=COMPANY, label=label)
	rows = {r.billrefnumber.split("-", 1)[1]: r.name for r in frappe.get_all("Mpesa C2B Payment Register", filters={"billrefnumber": ["like", f"{label}-%"]}, fields=["name", "billrefnumber"])}
	results = [
		_sell("600 = 100+200+300", 600, [rows["split-1 of 3"], rows["split-2 of 3"], rows["split-3 of 3"]]),
		_sell("500 = 250+450", 500, [rows["straddle-A"], rows["straddle-B"]]),
		_sell("200 paid 5000", 200, [rows["overpay"]]),
	]
	frappe.db.commit()
	print(json.dumps(results, default=str, indent=1))

	straddle, overpay = results[1], results[2]
	assert all(r["outstanding"] == 0 for r in results), "every sale settled"
	assert straddle["entries"][1][1] == 200.0, "the straddle residue sits on its own entry"
	assert overpay["entries"][0][1] == 4800.0 and overpay["change_amount"] == 0, "overpay stays as credit, no change"
	assert all(reg.payment_entry and reg.sales_invoice for r in results for reg in r["registers"]), "every register row points both ways"
	assert not any(g.voucher_no.startswith("POS-") for r in results for g in r["mpesa_gl"]), "the invoice posts no bank movement itself"
	print("ALL PROPERTIES HOLD")
	cleanup_qa_batch(label)
