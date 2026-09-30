"""Only cash is handed back at the till.

Card and M-Pesa cannot be refunded at the counter - accounts reverses them later with a
Payment Entry - so a return pays back at most the cash the drawer kept (Cash-type rows,
net of change, less cash already refunded), in one Cash row, and leaves the rest as the
customer's credit on the note. Returns count in the shift they happen in.
"""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from klik_pos.api.sales_invoice import create_partial_return, return_sales_invoice
from klik_pos.tests.test_mpesa_payment_entry_first import COMPANY, CUSTOMER, MpesaFirstCase

CARD = "_Test Klik Card"
CARD_ACCOUNT = "_Test Bank - _TC"


def _ensure_card_mode():
	if not frappe.db.exists("Mode of Payment", CARD):
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": CARD,
				"type": "Bank",
				"accounts": [{"company": COMPANY, "default_account": CARD_ACCOUNT}],
			}
		).insert(ignore_permissions=True)


class CashOnlyReturnCase(MpesaFirstCase):
	def setUp(self):
		super().setUp()
		_ensure_card_mode()

	def _sale(self, total, **tendered):
		"""A submitted sale today, paid {mode: amount}; Cash may be over-tendered."""
		invoice = self._draft(rate=total, posting_date=frappe.utils.nowdate())
		for mode, amount in tendered.items():
			invoice.append("payments", {"mode_of_payment": CARD if mode == "card" else "Cash", "amount": amount})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		return invoice

	def _full_return(self, invoice):
		result = return_sales_invoice(invoice.name)
		self.assertTrue(result.get("success"), result.get("message") or result.get("error"))
		return frappe.get_doc("Sales Invoice", result["return_invoice"])

	def _partial_return(self, invoice, amount, mode="Cash"):
		item = invoice.items[0]
		result = create_partial_return(
			invoice_name=invoice.name,
			return_items=[{"item_code": item.item_code, "return_qty": item.qty}],
			payment_method=mode,
			return_amount=amount,
		)
		self.assertTrue(result.get("success"), result.get("message") or result.get("error"))
		return frappe.get_doc("Sales Invoice", result["return_invoice"])

	@staticmethod
	def _refund_rows(credit):
		return [(p.mode_of_payment, flt(p.amount)) for p in credit.payments if flt(p.amount)]

	def _card_gl(self, voucher):
		return frappe.db.sql(
			"select count(*) from `tabGL Entry` where voucher_no=%s and account=%s and is_cancelled=0",
			(voucher, CARD_ACCOUNT),
		)[0][0]


class TestFullReturn(CashOnlyReturnCase):
	def test_a_cash_sale_refunds_the_cash_kept_net_of_change(self):
		credit = self._full_return(self._sale(600, cash=650))
		self.assertEqual(self._refund_rows(credit), [("Cash", -600)])

	def test_a_card_sale_refunds_nothing_and_leaves_the_value_as_credit(self):
		credit = self._full_return(self._sale(500, card=500))
		self.assertEqual(self._refund_rows(credit), [], "a card is refunded by accounts, not the till")
		self.assertEqual(self._card_gl(credit.name), 0, "no card money moves")
		self.assertEqual(flt(abs(credit.outstanding_amount)), 500, "the customer is owed it")

	def test_a_split_sale_refunds_only_its_cash_net_of_change(self):
		"""Cash 700 tendered with 200 change + Card 500 for 1000: 500 cash was kept."""
		credit = self._full_return(self._sale(1000, cash=700, card=500))
		self.assertEqual(self._refund_rows(credit), [("Cash", -500)])
		self.assertEqual(self._card_gl(credit.name), 0)
		self.assertEqual(flt(abs(credit.outstanding_amount)), 500, "the card half stays owed")

	def test_the_return_counts_in_the_shift_it_happens_in(self):
		from klik_pos.tests.test_opening_conflict import _profile, _shift

		profile = _profile()
		yesterday, today = _shift(profile, "Administrator", status="Closed", days_ago=1), _shift(profile, "Administrator")
		invoice = self._sale(300, cash=300)
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_pos_opening_entry", yesterday, update_modified=False)
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=today):
			credit = self._full_return(invoice)
		self.assertEqual(credit.custom_pos_opening_entry, today)


class TestPartialReturn(CashOnlyReturnCase):
	def test_a_card_sale_pays_no_cash_back(self):
		credit = self._partial_return(self._sale(500, card=500), 500, mode="Cash")
		self.assertEqual(self._refund_rows(credit), [])
		self.assertEqual(flt(abs(credit.outstanding_amount)), 500)

	def test_a_non_cash_refund_mode_is_refused(self):
		with self.assertRaisesRegex(Exception, "Only cash"):
			result = create_partial_return(
				invoice_name=(sale := self._sale(300, cash=300)).name,
				return_items=[{"item_code": sale.items[0].item_code, "return_qty": 1}],
				payment_method=CARD,
				return_amount=300,
			)
			if not result.get("success"):
				raise Exception(result.get("message") or result.get("error"))

	def test_cash_already_refunded_is_not_refunded_again(self):
		"""Two lines of 300, paid Cash 300 + Card 300. The first return takes the 300 cash;
		the second has no cash left to hand back - the card half stays as credit."""
		invoice = self._draft(rate=300, qty=2, posting_date=frappe.utils.nowdate())
		invoice.append("payments", {"mode_of_payment": "Cash", "amount": 300})
		invoice.append("payments", {"mode_of_payment": CARD, "amount": 300})
		invoice.save(ignore_permissions=True)
		invoice.submit()
		item = invoice.items[0].item_code

		first = frappe.get_doc(
			"Sales Invoice",
			create_partial_return(invoice_name=invoice.name, return_items=[{"item_code": item, "return_qty": 1}], payment_method="Cash", return_amount=300)["return_invoice"],
		)
		second = frappe.get_doc(
			"Sales Invoice",
			create_partial_return(invoice_name=invoice.name, return_items=[{"item_code": item, "return_qty": 1}], payment_method="Cash", return_amount=300)["return_invoice"],
		)

		self.assertEqual(self._refund_rows(first), [("Cash", -300)])
		self.assertEqual(self._refund_rows(second), [], "the card half is not paid out in cash")
		self.assertEqual(flt(abs(second.outstanding_amount)), 300)
