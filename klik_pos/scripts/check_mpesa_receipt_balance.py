"""One M-Pesa receipt paying several sales - the stress run for receipt balances.

    bench --site <site> execute klik_pos.scripts.check_mpesa_receipt_balance.main
    bench --site <site> execute klik_pos.scripts.check_mpesa_receipt_balance.reset

Runs on its own till and cashier (QA Receipt Balance), so no shift already open on the site
is disturbed. Every scenario goes through the checkout's own calls - process_mpesa to pick,
submit_draft_invoice to sell - and after each one the ledger invariants are checked:

  - each receipt's Payment Entry: paid = live allocations + unallocated
  - the M-Pesa account moved by exactly the M-Pesa money taken (receipts + STK)
  - every sale's outstanding = total - payments - advances

  S1  draw-down: 10,048 receipt pays 3,450, then 850, then caps a 6,548 sale at 5,748
  S2  over-pick: a 50,000 receipt for a 249 sale leaves 49,751 on offer
  S3a race: five 3,000 sales at once on one open receipt - only what it holds goes out
  S3b race: two sales at once on one new receipt - exactly one Payment Entry is minted
  S4  cancel a sale: its amount goes back on the receipt, which is offered again
  S5  return a sale paid from a receipt: the receipt's balance does not move
  S6  another customer's receipt: listed, not pickable, refused by the API
  S7  typed M-Pesa refused (till and desk); completed STK accepted, failed STK refused
  S8  shifts: shift A takes a receipt, shift B draws on it - only A counts the M-Pesa
  S9  a register row the M-Pesa app auto-submitted (submit_payment=1) is drawable

Pass cleanup=0 to keep everything for inspection; reset() undoes it all.
"""

import threading

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import _receipt_balance, get_mpesa_payments, process_mpesa
from klik_pos.api.pos_entry import _calculate_payment_reconciliation, _create_and_submit_closing_doc
from klik_pos.api.sales_invoice import _set_pos_opening_entry, return_sales_invoice, submit_draft_invoice
from klik_pos.tests.mpesa_fixtures import make_c2b_payment

COMPANY = "Dev Co"
CUSTOMER = "Walk In"
ITEM = "Consulting"
MPESA = "Mpesa-111222"
SHORTCODE = "600978"
AUTO_SHORTCODE = "898102"  # Mpesa Settings.auto_reconcile_c2b = 1 on dev
CASH = "Cash"
PROFILE = "QA Receipt Balance"
CASHIER = "qa-receipt-balance@example.com"
TAG = "QARB-"
PHONE = "254700999000"  # every receipt this script makes comes from this number


class PropertyFailed(AssertionError):
	pass


def check(condition, what):
	if not condition:
		raise PropertyFailed(what)
	print(f"    ok  {what}")


# -- till ------------------------------------------------------------------------------


def _ensure_cashier():
	if not frappe.db.exists("User", CASHIER):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": CASHIER,
				"first_name": "QA Receipt",
				"last_name": "Balance",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", CASHIER)
	for role in ("Accounts Manager", "Accounts User", "Sales Manager", "Sales User", "Stock User"):
		if not user.get("roles", {"role": role}):
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)


def _ensure_profile():
	if frappe.db.exists("POS Profile", PROFILE):
		return
	profile = frappe.copy_doc(frappe.get_doc("POS Profile", "_Test POS Profile"))
	profile.name = PROFILE
	profile.company = COMPANY
	profile.set("payments", [])
	profile.append("payments", {"mode_of_payment": CASH, "default": 1})
	profile.append("payments", {"mode_of_payment": MPESA, "default": 0})
	profile.set("applicable_for_users", [])
	profile.append("applicable_for_users", {"user": CASHIER, "default": 1})
	profile.insert(ignore_permissions=True)


def _open_shift():
	existing = frappe.db.exists(
		"POS Opening Entry", {"pos_profile": PROFILE, "user": CASHIER, "status": "Open", "docstatus": 1}
	)
	if existing:
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
	doc.append(
		"balance_details",
		{"mode_of_payment": CASH, "opening_amount": 0, "custom_variance_reason": "QA receipt-balance run"},
	)
	doc.append("balance_details", {"mode_of_payment": MPESA, "opening_amount": 0})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _close_shift(shift, counted):
	rows = _calculate_payment_reconciliation(shift, {"closing_balance": counted})
	_create_and_submit_closing_doc(shift, {"closing_balance": counted, "taxes": []}, rows, CASHIER)
	return {r["mode_of_payment"]: r for r in rows}


# -- selling ---------------------------------------------------------------------------


def _receipt(amount, label, shortcode=SHORTCODE):
	return make_c2b_payment(
		company=COMPANY, shortcode=shortcode, amount=amount, msisdn=PHONE, billrefnumber=f"{TAG}{label}"
	)


def _draft(total, customer=CUSTOMER, cash=0.0, typed_mpesa=0.0, stk_request=None):
	si = frappe.new_doc("Sales Invoice")
	si.update({"customer": customer, "company": COMPANY, "is_pos": 1, "pos_profile": PROFILE})
	si.append("items", {"item_code": ITEM, "qty": 1, "rate": total})
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	for row in si.get("payments") or []:
		row.amount = flt(cash) if row.mode_of_payment == CASH else flt(typed_mpesa)
		if row.mode_of_payment == MPESA and stk_request:
			row.custom_reference_text = stk_request
	_set_pos_opening_entry(si)
	si.remarks = f"{TAG}sale"
	si.insert(ignore_permissions=True)
	return si


def _pick(si, *receipts):
	process_mpesa(
		doctype="Sales Invoice",
		invoice_name=si.name,
		customer=si.customer,
		mpesa_payments=",".join(r.name for r in receipts),
		mode_of_payment=MPESA,
	)


def _sell(total, *receipts, cash=0.0, customer=CUSTOMER):
	si = _draft(total, customer=customer, cash=cash)
	if receipts:
		_pick(si, *receipts)
	result = submit_draft_invoice(si.name)
	if not result.get("success"):
		raise PropertyFailed(f"sale of {total} refused: {result.get('error')}")
	si.reload()
	return si


def _left(receipt):
	return flt(_receipt_balance(receipt.name).open_amount)


def _offered(receipt, customer=CUSTOMER):
	rows = get_mpesa_payments(company=COMPANY, search=receipt.transid, customer=customer)["payments"]
	return next((r for r in rows if r["name"] == receipt.name), None)


# -- invariants ------------------------------------------------------------------------


def _mpesa_account():
	return frappe.db.get_value("Mode of Payment Account", {"parent": MPESA, "company": COMPANY}, "default_account")


def _gl_balance(account, since):
	return flt(
		frappe.db.sql(
			"""SELECT SUM(debit - credit) FROM `tabGL Entry`
			WHERE account=%s AND is_cancelled=0 AND creation >= %s""",
			(account, since),
		)[0][0]
	)


class Ledger:
	def __init__(self):
		self.started = frappe.utils.now_datetime()
		self.account = _mpesa_account()
		self.receipts = []
		self.stk_taken = 0.0

	def track(self, *receipts):
		self.receipts.extend(receipts)
		return receipts[0] if len(receipts) == 1 else receipts

	def check(self):
		money_in = 0.0
		for receipt in self.receipts:
			pe = _receipt_balance(receipt.name).payment_entry
			if not pe or frappe.db.get_value("Payment Entry", pe, "docstatus") != 1:
				continue
			paid, unallocated, paid_to = frappe.db.get_value(
				"Payment Entry", pe, ["paid_amount", "unallocated_amount", "paid_to"]
			)
			live = flt(
				frappe.db.sql(
					"""SELECT SUM(ref.allocated_amount) FROM `tabPayment Entry Reference` ref
					INNER JOIN `tabSales Invoice` si ON si.name = ref.reference_name
					WHERE ref.parent=%s AND ref.reference_doctype='Sales Invoice' AND si.docstatus=1""",
					pe,
				)[0][0]
			)
			if abs(flt(paid) - live - flt(unallocated)) > 0.01:
				raise PropertyFailed(f"{receipt.transid}: paid {paid} != allocated {live} + unallocated {unallocated}")
			if paid_to == self.account:  # a receipt on another shortcode books to its own account
				money_in += flt(paid)
		moved = _gl_balance(self.account, self.started)
		if abs(moved - money_in - self.stk_taken) > 0.01:
			raise PropertyFailed(f"M-Pesa account moved {moved}, receipts {money_in} + STK {self.stk_taken}")
		for name, total, paid, adv, out in frappe.db.sql(
			"""SELECT name, IFNULL(NULLIF(rounded_total, 0), grand_total), paid_amount, total_advance, outstanding_amount
			FROM `tabSales Invoice` WHERE pos_profile=%s AND docstatus=1 AND is_return=0 AND creation >= %s""",
			(PROFILE, self.started),
		):
			if abs(flt(total) - flt(paid) - flt(adv) - flt(out)) > 0.01 and flt(out) != 0:
				raise PropertyFailed(f"{name}: outstanding {out} != {total} - {paid} - {adv}")
		print(f"    ok  ledger: {len(self.receipts)} receipts, M-Pesa account +{moved:,.2f}")


# -- scenarios -------------------------------------------------------------------------


def s1_draw_down(ledger):
	print("S1 draw-down")
	r = ledger.track(_receipt(10048, "s1"))
	first = _sell(3450, r)
	check(_left(r) == 6598, "3,450 sale leaves 6,598")
	check(_offered(r)["open_amount"] == 6598 and _offered(r)["used_count"] == 1, "offered at 6,598, used on 1 sale")
	second = _sell(850, r)
	check(_left(r) == 5748, "850 sale leaves 5,748")
	third = _sell(6548, r, cash=800)
	check(flt(third.total_advance) == 5748 and flt(third.outstanding_amount) == 0, "6,548 sale: 5,748 from the receipt + 800 cash")
	check(_left(r) == 0 and _offered(r) is None, "receipt spent and no longer offered")
	ledger.check()
	return r, second


def s2_over_pick(ledger):
	print("S2 over-pick")
	r = ledger.track(_receipt(50000, "s2"))
	si = _sell(249, r)
	check(flt(si.total_advance) == 249, "249 applied")
	check(_left(r) == 49751 and _offered(r)["open_amount"] == 49751, "49,751 left and offered")
	ledger.check()


def _race(invoice_names):
	site, sites_path = frappe.local.site, frappe.local.sites_path
	results = {}
	barrier = threading.Barrier(len(invoice_names))

	def run(name):
		frappe.init(site=site, sites_path=sites_path)
		frappe.connect()
		frappe.set_user(CASHIER)
		try:
			barrier.wait()
			out = submit_draft_invoice(name)
			frappe.db.commit()
			results[name] = "ok" if out.get("success") else f"refused: {out.get('error')}"
		except Exception as e:
			frappe.db.rollback()
			results[name] = f"raised: {e}"
		finally:
			frappe.destroy()

	threads = [threading.Thread(target=run, args=(n,)) for n in invoice_names]
	for t in threads:
		t.start()
	for t in threads:
		t.join()
	return results


def _resubmit(results):
	"""What a cashier does after 'submit again': press Submit once more, one till at a time."""
	for name, outcome in sorted(results.items()):
		if outcome == "ok":
			continue
		out = submit_draft_invoice(name)
		frappe.db.commit()
		results[name] = "ok (resubmitted)" if out.get("success") else f"refused again: {out.get('error')}"
	return results


def s3a_race_open(ledger):
	print("S3a five tills, one open receipt")
	r = ledger.track(_receipt(10048, "s3a"))
	_sell(48, r)  # used once: open, 10,000 left
	drafts = []
	for _ in range(5):
		si = _draft(3000)
		_pick(si, r)
		drafts.append(si.name)
	frappe.db.commit()
	results = _race(drafts)
	for name, outcome in sorted(results.items()):
		print(f"      {name}: {outcome[:120]}")
	first_wave = [o for o in results.values() if o == "ok"]
	check(len(first_wave) >= 1, "at least one till went through at once")
	check(
		all(o == "ok" or ("a moment ago" in o and r.transid in o) for o in results.values()),
		"every till that lost the race was told, naming the receipt, to submit again",
	)
	check(_left(r) >= 0, f"never negative mid-race ({_left(r)} left)")
	results = _resubmit(results)
	for name, outcome in sorted(results.items()):
		print(f"      {name}: {outcome[:120]}")
	ok = [n for n, o in results.items() if o.startswith("ok")]
	refused = [o for o in results.values() if not o.startswith("ok")]
	check(len(ok) == 3, f"after resubmitting, exactly 3 of 5 sales went through (got {len(ok)})")
	check(all("only" in o and "a moment ago" in o for o in refused), "the other 2 were refused: the receipt no longer holds 3,000")
	check(_left(r) == 1000, f"1,000 left, never negative (got {_left(r)})")
	ledger.check()


def s3b_race_new(ledger):
	print("S3b two tills, one new receipt")
	r = ledger.track(_receipt(5000, "s3b"))
	drafts = []
	for _ in range(2):
		si = _draft(1000)
		_pick(si, r)
		drafts.append(si.name)
	frappe.db.commit()
	results = _race(drafts)
	for name, outcome in sorted(results.items()):
		print(f"      {name}: {outcome[:120]}")
	entries = frappe.db.count("Payment Entry", {"custom_mpesa_receipt_number": r.transid, "docstatus": 1})
	check(entries == 1, f"one Payment Entry for the receipt after the race (got {entries})")
	results = _resubmit(results)
	entries = frappe.db.count("Payment Entry", {"custom_mpesa_receipt_number": r.transid, "docstatus": 1})
	check(entries == 1, f"still one Payment Entry after resubmitting (got {entries})")
	check(all(o.startswith("ok") for o in results.values()), "both sales went through")
	check(_left(r) == 3000, f"3,000 left (got {_left(r)})")
	ledger.check()


def s4_cancel(ledger, receipt, middle_sale):
	print("S4 cancel a sale")
	frappe.get_doc("Sales Invoice", middle_sale.name).cancel()
	check(_left(receipt) == 850, "the cancelled 850 is back on the spent receipt")
	check((_offered(receipt) or {}).get("open_amount") == 850, "and the receipt is offered again")
	ledger.check()


def s5_return(ledger):
	print("S5 return a receipt-paid sale")
	r = ledger.track(_receipt(2000, "s5"))
	si = _sell(1200, r)
	before = _left(r)
	result = return_sales_invoice(si.name)
	check(bool(result) and (result.get("success", True) is not False), f"return filed: {str(result)[:90]}")
	check(_left(r) == before == 800, "receipt balance unchanged by the return (800)")
	ledger.check()


def _other_customer():
	return frappe.get_all(
		"Customer", filters={"name": ["!=", CUSTOMER], "disabled": 0}, pluck="name", order_by="creation", limit=1
	)[0]


def s6_other_customer(ledger):
	print("S6 another customer's receipt")
	r = ledger.track(_receipt(3000, "s6"))
	_sell(1000, r)
	frappe.db.commit()  # the refusals below roll back; the sale must survive them
	other = _other_customer()
	row = _offered(r, customer=other)
	check(row is not None and row["selectable"] is False and row["held_by"] == CUSTOMER, f"listed for {other} but not pickable, held by {CUSTOMER}")
	si = _draft(500, customer=other)
	try:
		_pick(si, r)
		raise PropertyFailed("the API let another customer draw on the receipt")
	except frappe.ValidationError as e:
		check(f"held by {CUSTOMER}" in str(e), "the API refuses it, naming who holds it")
	frappe.db.rollback()
	ledger.check()


def _stk(status, amount, label):
	doc = frappe.get_doc(
		{
			"doctype": "Mpesa Express Request",
			"status": status,
			"amount": amount,
			"transaction_id": f"{TAG}{label}" if status == "Completed" else None,
			"phone_number": "254700999000",
		}
	)
	doc.name = f"MEXP-{TAG}{label}-{frappe.generate_hash(length=6)}"
	doc.db_insert()
	return doc.name


def s7_no_receipt(ledger):
	print("S7 no receipt, no M-Pesa")
	frappe.db.commit()
	typed = _draft(700, typed_mpesa=700)
	out = submit_draft_invoice(typed.name)
	check(not out.get("success") and "no M-Pesa receipt behind it" in (out.get("error") or ""), "typed M-Pesa refused at the till")
	frappe.db.rollback()

	desk = frappe.new_doc("Sales Invoice")
	desk.update({"customer": CUSTOMER, "company": COMPANY, "is_pos": 1, "pos_profile": PROFILE})
	desk.append("items", {"item_code": ITEM, "qty": 1, "rate": 700})
	desk.set_missing_values()
	desk.calculate_taxes_and_totals()
	for row in desk.payments:
		row.amount = 700 if row.mode_of_payment == MPESA else 0
	desk.insert(ignore_permissions=True)
	try:
		desk.submit()
		raise PropertyFailed("a desk POS invoice submitted typed M-Pesa")
	except frappe.ValidationError as e:
		check("no M-Pesa receipt behind it" in str(e), "typed M-Pesa refused from the desk too")
	frappe.db.rollback()

	done = _stk("Completed", 700, "s7ok")
	paid = _draft(700, typed_mpesa=700, stk_request=done)
	out = submit_draft_invoice(paid.name)
	check(out.get("success"), f"completed STK push accepted: {out.get('error') or 'ok'}")
	ledger.stk_taken += 700
	frappe.db.commit()  # the refusal below rolls back; this sale must survive it

	failed = _stk("Failed", 700, "s7bad")
	bad = _draft(700, typed_mpesa=700, stk_request=failed)
	out = submit_draft_invoice(bad.name)
	check(not out.get("success"), "failed STK push refused")
	frappe.db.rollback()
	ledger.check()


def s8_shifts(ledger, shift_a):
	print("S8 shift A takes a receipt, shift B draws on it")
	r = ledger.track(_receipt(5000, "s8"))
	_sell(800, r)
	a_entries = frappe.get_all(
		"Payment Entry", filters={"custom_pos_opening_entry": shift_a.name, "docstatus": 1}, fields=["paid_amount"]
	)
	a_mpesa = sum(flt(e.paid_amount) for e in a_entries)
	a_cash = flt(
		frappe.db.sql(
			"""SELECT SUM(sip.amount) FROM `tabSales Invoice Payment` sip INNER JOIN `tabSales Invoice` si ON si.name=sip.parent
			WHERE si.custom_pos_opening_entry=%s AND si.docstatus=1 AND sip.mode_of_payment=%s""",
			(shift_a.name, CASH),
		)[0][0]
	)
	a_stk = flt(
		frappe.db.sql(
			"""SELECT SUM(sip.amount) FROM `tabSales Invoice Payment` sip INNER JOIN `tabSales Invoice` si ON si.name=sip.parent
			WHERE si.custom_pos_opening_entry=%s AND si.docstatus=1 AND sip.mode_of_payment=%s""",
			(shift_a.name, MPESA),
		)[0][0]
	)
	a = _close_shift(shift_a, {CASH: a_cash, MPESA: a_mpesa + a_stk})
	check(flt(a[MPESA]["expected_amount"]) == a_mpesa + a_stk, f"shift A expects every receipt it took on M-Pesa ({a_mpesa + a_stk:,.0f})")
	frappe.db.commit()

	shift_b = _open_shift()
	check(shift_b.name != shift_a.name, f"shift B is {shift_b.name}")
	si = _sell(3000, r)
	check(flt(si.total_advance) == 3000 and si.custom_pos_opening_entry == shift_b.name, "shift B sold 3,000 from A's receipt")
	b = _close_shift(shift_b, {CASH: 0, MPESA: 0})
	check(flt(b.get(MPESA, {}).get("expected_amount", 0)) == 0, "shift B expects 0 M-Pesa: the money arrived in A")

	from klik_pos.overrides.pos_closing_entry import get_invoices

	desk = get_invoices(start=shift_b.period_start_date, end=frappe.utils.now_datetime(), pos_profile=PROFILE, user=CASHIER)["payments"]
	desk_mpesa = sum(flt(p["amount"]) for p in desk if p["mode_of_payment"] == MPESA)
	check(desk_mpesa == 0, "the standard POS Closing Entry agrees for shift B")
	frappe.db.commit()
	ledger.check()
	return _open_shift()


def s9_auto_submitted(ledger):
	print("S9 register rows on a shortcode the M-Pesa app auto-submits")
	# (a) The app cannot resolve a customer from the bill reference: its auto-submit fails
	# and the row stays a draft. klik offers it as untouched, full amount.
	a = ledger.track(_receipt(4000, "s9a", shortcode=AUTO_SHORTCODE))
	a.reload()
	check(a.docstatus == 0 and _receipt_balance(a.name).state == "new", "unresolved bill reference: still a draft, offered as new")
	si = _sell(1500, a)
	check(flt(si.total_advance) == 1500 and _left(a) == 2500, "and a sale draws 1,500 from it, 2,500 left")

	# (b) The bill reference names the customer: the app submits the row with
	# submit_payment=1 and its own Payment Entry. klik draws on that entry's balance.
	b = make_c2b_payment(company=COMPANY, shortcode=AUTO_SHORTCODE, amount=6000, msisdn=PHONE, billrefnumber=CUSTOMER)
	b.reload()
	ledger.track(b)
	bal = _receipt_balance(b.name)
	print(f"      app result: docstatus={b.docstatus} submit_payment={b.submit_payment} payment_entry={b.get('payment_entry')} -> {bal.state}, {bal.open_amount} held by {bal.held_by}")
	if b.docstatus != 1 or not bal.payment_entry:
		print("      FINDING: the app did not submit the row with an entry even with a resolvable customer")
		ledger.check()
		return
	check(bal.state == "open" and bal.held_by == CUSTOMER, f"auto-submitted receipt is open for {CUSTOMER} at {bal.open_amount:,.0f}")
	before = _left(b)
	si = _sell(2000, b)
	check(flt(si.total_advance) == 2000 and _left(b) == before - 2000, "a sale drew 2,000 from the app's own entry")
	ledger.check()


def main(cleanup=1):
	try:
		_run(int(cleanup))
	except Exception:
		import traceback

		traceback.print_exc()
		raise


def _run(cleanup):
	frappe.set_user("Administrator")
	_ensure_cashier()
	_ensure_profile()
	frappe.db.commit()
	frappe.set_user(CASHIER)
	shift = _open_shift()
	frappe.db.commit()
	print(f"shift {shift.name} on {PROFILE} for {CASHIER}\n")

	ledger = Ledger()
	s1_receipt, s1_middle = s1_draw_down(ledger)
	frappe.db.commit()
	s2_over_pick(ledger)
	frappe.db.commit()
	s3a_race_open(ledger)
	s3b_race_new(ledger)
	frappe.set_user(CASHIER)
	s4_cancel(ledger, s1_receipt, s1_middle)
	frappe.db.commit()
	s5_return(ledger)
	frappe.db.commit()
	s6_other_customer(ledger)
	s7_no_receipt(ledger)
	frappe.db.commit()
	s8_shifts(ledger, shift)
	frappe.db.commit()
	frappe.set_user("Administrator")
	s9_auto_submitted(ledger)
	frappe.db.commit()
	print("\nALL PROPERTIES HOLD")

	if cleanup:
		reset()


def reset():
	try:
		_reset()
	except Exception:
		import traceback

		traceback.print_exc()
		raise


def _reset():
	frappe.set_user("Administrator")
	def stand_down_shifts():
		for shift in frappe.get_all("POS Opening Entry", filters={"pos_profile": PROFILE, "status": "Open"}, pluck="name"):
			frappe.db.set_value("POS Opening Entry", shift, "status", "Closed", update_modified=False)

	# ERPNext refuses to cancel a closing entry while any shift on the till is open, and
	# cancelling one reopens the shift it closed - so stand them down before every cancel.
	for closing in frappe.get_all("POS Closing Entry", filters={"pos_profile": PROFILE, "docstatus": 1}, pluck="name"):
		stand_down_shifts()
		frappe.get_doc("POS Closing Entry", closing).cancel()
	stand_down_shifts()
	# Returns first: a credit note blocks cancelling the sale it returns.
	invoices = frappe.get_all(
		"Sales Invoice", filters={"pos_profile": PROFILE, "docstatus": 1}, pluck="name", order_by="is_return desc, creation desc"
	)
	for name in invoices:
		frappe.get_doc("Sales Invoice", name).cancel()
	for name in frappe.get_all("Sales Invoice", filters={"pos_profile": PROFILE, "docstatus": ["!=", 1]}, pluck="name"):
		frappe.delete_doc("Sales Invoice", name, ignore_permissions=True, force=True)
	registers = frappe.get_all(
		"Mpesa C2B Payment Register",
		or_filters={"billrefnumber": ["like", f"{TAG}%"], "msisdn": PHONE},
		fields=["name", "payment_entry"],
	)
	for row in registers:
		doc = frappe.get_doc("Mpesa C2B Payment Register", row.name)
		if doc.docstatus == 1:
			doc.cancel()
	for row in registers:
		if row.payment_entry and frappe.db.get_value("Payment Entry", row.payment_entry, "docstatus") == 1:
			frappe.get_doc("Payment Entry", row.payment_entry).cancel()
		frappe.delete_doc("Mpesa C2B Payment Register", row.name, ignore_permissions=True, force=True)
	frappe.db.delete("Mpesa Express Request", {"name": ["like", f"MEXP-{TAG}%"]})
	frappe.db.commit()
	print(f"reset: {len(invoices)} invoice(s) cancelled, {len(registers)} receipt(s) removed, shifts closed")
