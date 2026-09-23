"""The Closing Shift counts money that settled a shift's sales through Payment Entries.

It summed the invoices' payment tables plus the Payment Entries stamped with the shift
(M-Pesa receipts). A customer advance an accountant recorded is stamped with nothing and
usually has no Mode of Payment, so a sale it settled was missing from every expected
amount - and, on a site where every sale is settled that way, the shift never balanced.
"""

import frappe
from frappe.utils import flt

from klik_pos.api.mpesa import _allocate_receipts_before_submit
from klik_pos.api.payment_rows import advance_payment_rows
from klik_pos.api.pos_entry import _calculate_payment_reconciliation
from klik_pos.tests.test_mpesa_payment_entry_first import MpesaFirstCase


class TestClosingCountsAdvances(MpesaFirstCase):
	def setUp(self):
		super().setUp()
		self.shift = f"TEST-OPE-ADV-{frappe.generate_hash(length=6)}"

	def test_an_unstamped_advance_without_a_mode_is_counted_under_its_accounts_mode(self):
		"""Cash 100 at the till; 150 arrived earlier as a plain advance into _Test Bank,
		which is Cheque's account. The shift expects Cash 100 and Cheque 150."""
		invoice, (entry,) = self._sale_with_advances(cash=100, receipts=[150])
		self._make_accountants_entry(entry)

		rows = self._reconcile()

		self.assertEqual(self._expected(rows, "Cash"), 100)
		self.assertEqual(self._expected(rows, "Cheque"), 150)

	def test_a_receipt_stamped_with_the_shift_is_still_counted_exactly_once(self):
		"""An M-Pesa receipt is both stamped with the shift and an advance on the invoice;
		reading the advances must not count it a second time."""
		invoice, (stamped, plain) = self._sale_with_advances(cash=100, receipts=[100, 150])
		frappe.db.set_value("Payment Entry", stamped, "custom_pos_opening_entry", self.shift, update_modified=False)
		self._make_accountants_entry(plain)

		rows = self._reconcile()

		self.assertEqual(self._expected(rows, "Cheque"), 250, "100 stamped once + 150 plain, not 350")

	def test_an_advance_into_an_account_with_no_mode_is_left_out_without_failing(self):
		invoice, (entry,) = self._sale_with_advances(cash=100, receipts=[150])
		self._make_accountants_entry(entry, paid_to="HDFC - _TC")

		rows = self._reconcile()

		self.assertEqual(self._expected(rows, "Cash"), 100)
		self.assertEqual(self._expected(rows, "Cheque"), 0)

	def _sale_with_advances(self, cash, receipts):
		invoice = self._draft(rate=cash + sum(receipts), posting_date=frappe.utils.nowdate())
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": cash})
		invoice.save(ignore_permissions=True)
		invoice = self._record(invoice, *[self._receipt(a, f"2547000005{i:02d}") for i, a in enumerate(receipts)])
		_allocate_receipts_before_submit(invoice)
		invoice.reload()
		invoice.submit()
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_pos_opening_entry", self.shift, update_modified=False)
		rows = sorted(advance_payment_rows([invoice.name])[invoice.name], key=lambda r: r["amount"])
		return invoice, [r["payment_entry"] for r in rows]

	def _make_accountants_entry(self, entry, paid_to=None):
		values = {"mode_of_payment": None, "custom_pos_opening_entry": None}
		if paid_to:
			values["paid_to"] = paid_to
		frappe.db.set_value("Payment Entry", entry, values, update_modified=False)

	def _reconcile(self):
		return _calculate_payment_reconciliation(
			frappe._dict(name=self.shift), {"closing_balance": {"Cash": 0, "Cheque": 0}}
		)

	def _expected(self, rows, mode):
		return flt(next(r for r in rows if r["mode_of_payment"] == mode)["expected_amount"])
