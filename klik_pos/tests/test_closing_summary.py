"""The Closing Shift's expected amounts come from the server.

The screen used to add up the invoices it had loaded: it stopped at 100 on a long shift, and
its own filters changed the figures. `pos_entry.expected_by_mode` is the one place the expected
amounts are worked out - the closing entry is filed from it and `closing_summary` shows it - so
what the cashier counts against is what gets filed.
"""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from klik_pos.api import pos_entry
from klik_pos.api.pos_entry import _calculate_payment_reconciliation, closing_summary, expected_by_mode
from klik_pos.tests.test_allow_closing_shift import CASHIER_ROLES, FIELD as ALLOW_CLOSING, ClosingCase
from klik_pos.tests.test_mpesa_payment_entry_first import MpesaFirstCase
from klik_pos.tests.test_shared_shift import OPENER

HIDE = "custom_hide_expected_amount"


class TestExpectedByMode(MpesaFirstCase):
	def setUp(self):
		super().setUp()
		self.shift = f"TEST-OPE-SUM-{frappe.generate_hash(length=6)}"

	def _sale(self, payments, total=None, is_return=False):
		invoice = self._draft(rate=total or sum(payments.values()))
		for mode, amount in payments.items():
			invoice.append("payments", {"mode_of_payment": mode, "amount": amount})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_pos_opening_entry", self.shift, update_modified=False)
		return invoice

	def test_the_cash_kept_per_mode_with_the_count_of_sales(self):
		self._sale({"Cash": 650}, total=600)  # 50 change
		self._sale({"Cash": 300})
		cash = expected_by_mode(self.shift)["Cash"]
		self.assertEqual(
			(flt(cash["opening_amount"]), flt(cash["sales_amount"]), flt(cash["expected_amount"]), cash["transactions"]),
			(0, 900, 900, 2),
		)

	def test_the_opening_float_is_part_of_what_is_expected(self):
		self._sale({"Cash": 300})
		with patch.object(pos_entry, "_opening_floats", return_value={"Cash": 1000.0}):
			cash = expected_by_mode(self.shift)["Cash"]
		self.assertEqual((flt(cash["opening_amount"]), flt(cash["expected_amount"])), (1000, 1300))

	def test_it_is_what_the_closing_entry_files(self):
		self._sale({"Cash": 650}, total=600)
		self._sale({"Cash": 200})
		expected = expected_by_mode(self.shift)
		filed = _calculate_payment_reconciliation(frappe._dict(name=self.shift), {"closing_balance": {"Cash": 800}})
		self.assertEqual(
			{r["mode_of_payment"]: flt(r["expected_amount"]) for r in filed},
			{mode: flt(row["expected_amount"]) for mode, row in expected.items()},
		)
		self.assertEqual(flt(next(r for r in filed if r["mode_of_payment"] == "Cash")["difference"]), 0)

	def test_an_empty_shift_expects_only_its_float(self):
		self.assertEqual(expected_by_mode(self.shift), {})


class TestClosingSummary(ClosingCase):
	"""The screen's figures: the caller's shift, guarded like the close itself."""

	def _summary(self, roles=CASHIER_ROLES, modes=None):
		modes = modes or {
			"Cash": {
				"mode_of_payment": "Cash",
				"opening_amount": 1000.0,
				"sales_amount": 500.0,
				"expected_amount": 1500.0,
				"transactions": 3,
			}
		}
		entry = frappe._dict(name=self.entry, pos_profile=self.till, user=OPENER)
		frappe.set_user(OPENER)
		with (
			self._as(roles),
			patch.object(pos_entry, "_get_open_pos_entry", return_value=entry),
			patch.object(pos_entry, "expected_by_mode", return_value=modes),
		):
			return closing_summary()

	def test_the_shift_s_modes_and_totals(self):
		frappe.db.set_value("POS Profile", self.till, ALLOW_CLOSING, 1)
		summary = self._summary()
		self.assertEqual(summary["opening_entry"], self.entry)
		self.assertFalse(summary["figures_hidden"])
		self.assertEqual(
			summary["modes"],
			[
				{
					"mode_of_payment": "Cash",
					"opening_amount": 1000.0,
					"sales_amount": 500.0,
					"expected_amount": 1500.0,
					"transactions": 3,
				}
			],
		)

	def test_hide_expected_amount_leaves_the_figures_out(self):
		frappe.db.set_value("POS Profile", self.till, {ALLOW_CLOSING: 1, HIDE: 1})
		summary = self._summary()
		self.assertTrue(summary["figures_hidden"])
		cash = summary["modes"][0]
		self.assertEqual(cash["mode_of_payment"], "Cash")
		self.assertEqual(cash["opening_amount"], 1000.0, "the float the cashier entered stays")
		self.assertEqual((cash["sales_amount"], cash["expected_amount"], cash["transactions"]), (0.0, 0.0, 0))

	def test_refused_where_closing_is_turned_off(self):
		# ClosingCase turns 'Allow Closing Shift' off on the till.
		with self.assertRaisesRegex(frappe.PermissionError, "Closing is turned off"):
			self._summary()
