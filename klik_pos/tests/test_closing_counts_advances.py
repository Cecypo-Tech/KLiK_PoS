"""The Closing Shift counts the money the till handled, and only that.

It sums the invoices' payment tables plus the Payment Entries stamped with the shift
(M-Pesa receipts taken at the till). Money that settled a sale from outside the POS - a
customer advance an accountant recorded, with or without a Mode of Payment - is shown on
the invoice but was never in the cashier's hands, so it is not theirs to count.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import _allocate_receipts_before_submit
from klik_pos.api.payment_rows import advance_payment_rows
from klik_pos.api.pos_entry import _calculate_payment_reconciliation
from klik_pos.tests.test_mpesa_payment_entry_first import MODE, MpesaFirstCase


class TestClosingCountsTillMoneyOnly(MpesaFirstCase):
	def setUp(self):
		super().setUp()
		self.shift = f"TEST-OPE-ADV-{frappe.generate_hash(length=6)}"

	def test_an_advance_recorded_outside_the_pos_is_not_counted_whether_or_not_it_has_a_mode(self):
		"""Cash 100 at the till; 150 and 200 arrived earlier as advances nobody at the till
		took - one with a mode, one without. The shift expects Cash 100 and nothing else."""
		invoice, (with_mode, without_mode) = self._sale_with_advances(cash=100, receipts=[150, 200])
		self._make_outside_entry(with_mode, keep_mode=True)
		self._make_outside_entry(without_mode, keep_mode=False)

		rows = self._reconcile()

		self.assertEqual(self._expected(rows, "Cash"), 100)
		self.assertEqual(self._expected(rows, MODE), 0)

	def test_a_receipt_stamped_with_the_shift_is_counted_exactly_once(self):
		"""An M-Pesa receipt is both stamped with the shift and an advance on the invoice."""
		invoice, (stamped,) = self._sale_with_advances(cash=100, receipts=[150])
		frappe.db.set_value("Payment Entry", stamped, "custom_pos_opening_entry", self.shift, update_modified=False)

		rows = self._reconcile()

		self.assertEqual(self._expected(rows, MODE), 150)

	def test_a_mode_the_till_does_not_list_still_reaches_the_closing_entry(self):
		"""The till counts Cash alone, so the page sends no count for the receipt's mode.
		The 150 taken at the till is still expected, so the closing entry carries a row for
		it with a zero count rather than losing the money silently."""
		invoice, (stamped,) = self._sale_with_advances(cash=100, receipts=[150])
		frappe.db.set_value("Payment Entry", stamped, "custom_pos_opening_entry", self.shift, update_modified=False)

		rows = _calculate_payment_reconciliation(frappe._dict(name=self.shift), {"closing_balance": {"Cash": 0}})

		row = next(r for r in rows if r["mode_of_payment"] == MODE)
		self.assertEqual(flt(row["expected_amount"]), 150)
		self.assertEqual(flt(row["closing_amount"]), 0)
		self.assertEqual(flt(row["difference"]), -150)

	def _sale_with_advances(self, cash, receipts):
		invoice = self._draft(rate=cash + sum(receipts))
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": cash})
		invoice.save(ignore_permissions=True)
		invoice = self._record(invoice, *[self._receipt(a, f"2547000005{i:02d}") for i, a in enumerate(receipts)])
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_pos_opening_entry", self.shift, update_modified=False)
		rows = sorted(advance_payment_rows([invoice.name])[invoice.name], key=lambda r: r["amount"])
		return invoice, [r["payment_entry"] for r in rows]

	def _make_outside_entry(self, entry, keep_mode):
		values = {"custom_pos_opening_entry": None}
		if not keep_mode:
			values["mode_of_payment"] = None
		frappe.db.set_value("Payment Entry", entry, values, update_modified=False)

	def _reconcile(self):
		return _calculate_payment_reconciliation(
			frappe._dict(name=self.shift), {"closing_balance": {"Cash": 0, MODE: 0}}
		)

	def _expected(self, rows, mode):
		return flt(next(r for r in rows if r["mode_of_payment"] == mode)["expected_amount"])
