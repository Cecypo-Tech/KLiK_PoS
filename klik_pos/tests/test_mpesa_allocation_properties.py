"""Money rules for M-Pesa allocation, over randomised sales.

Whatever mix of receipts, earlier use, cash and vouchers a sale meets, it is either paid
in full or refused cleanly, and no receipt pays out more than it brought in. CS-02273
broke the first rule; no hand-written case had that exact shape.

Stdlib random with a printed seed, not Hypothesis: every case writes to the DB, so
shrinking would take minutes, and a failing seed replays exactly with
KLIK_PROPERTY_SEED=<seed>. KLIK_PROPERTY_CASES sets how many (default 25).
"""

import os
import random

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import (
	_allocate_receipts_before_submit,
	_finalize_mpesa_reconciliation,
	_receipt_balance,
)
from klik_pos.tests.test_mpesa_receipt_balance import ReceiptCase

CASES = int(os.environ.get("KLIK_PROPERTY_CASES", 25))
SEED = int(os.environ.get("KLIK_PROPERTY_SEED", 20261015))
TOL = 0.01


def scenario(rng):
	receipts = []
	for _ in range(rng.randint(1, 3)):
		amount = rng.choice([100, 250, 450, 1000, 5000])
		before = rng.choice([0, 0, amount // 2])  # used by another sale before the pick
		after = rng.choice([0, 0, (amount - before) // 2, amount - before])  # after the pick
		receipts.append((amount, before, after))
	sale = rng.choice([50, 100, 300, 700, 1200, 6000])
	return {
		"receipts": receipts,
		"sale": sale,
		"cash": rng.choice([0, 0, sale // 2]),
		"voucher": rng.choice([0, 0, sale // 4]),
	}


# Named shapes that must always be in the run, whatever the seed.
KNOWN = {
	"CS-02273 receipt spent after the pick": {"receipts": [(1000, 0, 1000)], "sale": 800, "cash": 0, "voucher": 0},
	"partly drained, still covers": {"receipts": [(1000, 0, 100)], "sale": 800, "cash": 0, "voucher": 0},
	"drained, cash covers the rest": {"receipts": [(1000, 0, 500)], "sale": 800, "cash": 300, "voucher": 0},
	"first drained, second covers (D1)": {"receipts": [(300, 0, 300), (1000, 0, 0)], "sale": 800, "cash": 0, "voucher": 0},
	"first part-drained, later receipts cover (D1)": {
		"receipts": [(5000, 0, 2500), (450, 0, 0), (100, 0, 50)], "sale": 6000, "cash": 3000, "voucher": 0,
	},
	"first drained, sale still short (refuse)": {"receipts": [(300, 0, 300), (250, 0, 0)], "sale": 800, "cash": 0, "voucher": 0},
	# rounded_total (800) differs from grand_total (799.6): the receipt pays what is rounded.
	"rounding: 799.6 paid by an 800 receipt": {"receipts": [(800, 0, 0)], "sale": 799.6, "cash": 0, "voucher": 0},
	# 800 - 699.9 leaves 100.10000000000002 in floats; the 100.1 receipt covers it.
	"sub-cent float leftover after a drain": {
		"receipts": [(300, 0, 300), (100.1, 0, 0)], "sale": 800, "cash": 699.9, "voucher": 0,
	},
}


class TestAllocationRules(ReceiptCase):
	def run_case(self, case, sc):
		receipts = []
		for amount, before, after in sc["receipts"]:
			receipt = self._receipt(amount)
			if before:
				self._sell(before, receipt)
			receipts.append((receipt, after))
		invoice = self._draft(rate=sc["sale"])
		if sc["cash"]:
			invoice.append("payments", {"mode_of_payment": "Cash", "amount": sc["cash"]})
			invoice.save()
		try:
			self._record(invoice, *[r for r, _ in receipts])
		except frappe.ValidationError as e:
			return "refused_at_pick", invoice, receipts, str(e)
		# What the cashier picked; a sale short before any other till touched it is the
		# checkout's business (a credit sale may be), not the allocator's.
		sc["picked"] = sum(flt(c.amount) for c in invoice.custom_mpesa_reconciled_payments)
		for receipt, after in receipts:
			if after:
				self._sell(after, receipt)  # another till, after our pick
		invoice.reload()
		invoice._klik_credit_reserved = sc["voucher"]

		frappe.db.savepoint("klik_case")
		try:
			summary = _allocate_receipts_before_submit(invoice)
			invoice.submit()
			_finalize_mpesa_reconciliation(invoice, summary)
		except frappe.ValidationError as e:
			# A real checkout rolls the request back; so does this.
			frappe.db.rollback(save_point="klik_case")
			return "refused", invoice, receipts, str(e)
		invoice.reload()
		return "submitted", invoice, receipts, None

	def check_rules(self, case, sc, outcome, invoice, receipts, message):
		ctx = f"\n{case}: {sc}\nseed={SEED} outcome={outcome} message={message}"
		for receipt, _ in receipts:
			entries = frappe.get_all(
				"Payment Entry",
				{"custom_mpesa_receipt_number": receipt.transid, "docstatus": 1},
				["name", "paid_amount", "unallocated_amount"],
			)
			self.assertLessEqual(len(entries), 1, f"one receipt, one entry{ctx}")
			for pe in entries:
				self.assertAlmostEqual(flt(pe.paid_amount), flt(receipt.transamount), 2, f"entry is the whole receipt{ctx}")
				self.assertGreaterEqual(flt(pe.unallocated_amount), -TOL, f"receipt overdrawn{ctx}")
				allocated = flt(frappe.db.sql(
					"SELECT SUM(allocated_amount) FROM `tabPayment Entry Reference` WHERE parent=%s", pe.name
				)[0][0])
				self.assertLessEqual(allocated, flt(pe.paid_amount) + TOL, f"receipt paid out more than it took{ctx}")

		if outcome == "submitted":
			# Only the voucher's share, and whatever was already short at the pick, may stay
			# owing; vouchers settle right after submit.
			payable = flt(invoice.rounded_total) or flt(invoice.grand_total)
			short_at_pick = max(payable - sc["picked"] - sc["cash"] - sc["voucher"], 0)
			self.assertLessEqual(
				flt(invoice.outstanding_amount), sc["voucher"] + short_at_pick + TOL, f"posted short{ctx}"
			)
		elif outcome == "refused":
			self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "docstatus"), 0, f"refused but not a draft{ctx}")
			# D1: refuse only when the money left can't cover the sale.
			left = sum(flt(_receipt_balance(r.name).open_amount) for r, _ in receipts)
			payable = flt(invoice.rounded_total) or flt(invoice.grand_total)
			self.assertLess(left + sc["cash"] + sc["voucher"], payable - TOL, f"refused a sale the money covers{ctx}")

	def test_known_shapes(self):
		for case, sc in KNOWN.items():
			with self.subTest(case):
				self.check_rules(case, sc, *self.run_case(case, sc))

	def test_random_sales(self):
		rng = random.Random(SEED)
		outcomes = []
		for i in range(CASES):
			sc = scenario(rng)
			outcome, *rest = self.run_case(f"case {i}", sc)
			outcomes.append(outcome)
			with self.subTest(i=i):
				self.check_rules(f"case {i}", sc, outcome, *rest)
		reached = sum(o != "refused_at_pick" for o in outcomes)
		self.assertGreaterEqual(reached, CASES // 2, "most cases never reached the allocator; fix the generator")
		# A run that never submits, or never refuses, checked only half the rules.
		self.assertIn("submitted", outcomes, f"seed={SEED}: no case submitted")
		self.assertIn("refused", outcomes, f"seed={SEED}: no case was refused")
