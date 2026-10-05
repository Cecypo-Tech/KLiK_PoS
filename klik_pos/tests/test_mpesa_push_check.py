"""An STK push whose confirmation never arrived: "Check with M-Pesa" asks Safaricom, and when it
says paid - an answer with no receipt number - the sale submits on it. The receipt number follows
when the receipt reaches the register (frappe_mpsa_payments matches it to the push).

Safaricom is never called: check_transaction_status and pull_transactions are mocked (dev's
sandbox shortcode cannot use the Pull API either).
"""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from klik_pos.api import mpesa, mpesa_order, sales_order
from klik_pos.api.mpesa_order import check_mpesa_push
from klik_pos.tests.mpesa_fixtures import make_c2b_payment
from klik_pos.tests.test_held_order_orphans import COMPANY
from klik_pos.tests.test_mpesa_order_checkout import _at_till, _order

EXPRESS = "Mpesa Express Request"
PHONE = "254700000123"
CHECK = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.check_transaction_status"
PULL = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.pull_transactions"
REGISTER = "Mpesa C2B Payment Register"


class PushCase(FrappeTestCase):
	"""An M-Pesa order, its shortcode's settings, and a push for 450 sent from the order."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		# The check limit counts in Redis, which the rollback does not undo.
		frappe.cache.delete_keys("klik_mpesa_checks:")
		self.shortcode = f"TPC{frappe.generate_hash(length=6).upper()}"
		self.settings = f"_Test Push Check {self.shortcode}"
		frappe.get_doc(
			{
				"doctype": "Mpesa Settings",
				"name": self.settings,
				"payment_gateway_name": self.settings,
				"company": COMPANY,
				"business_shortcode": self.shortcode,
			}
		).db_insert()
		self.order = _order()
		self.push = self._push()

	def _push(self, status="In Progress", **fields):
		doc = frappe.get_doc(
			{
				"doctype": EXPRESS,
				"name": f"_Test MEXP {frappe.generate_hash(length=8)}",
				"docstatus": 1,
				"status": status,
				"reference_doctype": "Sales Order",
				"reference_name": self.order,
				"account_reference": self.order,
				"phone_number": PHONE,
				"currency": "KES",
				"base_amount": 450,
				"amount": 450,
				"settings": self.settings,
				**fields,
			}
		)
		doc.db_insert()
		return doc.name


class TestCheckWithMpesa(PushCase):
	def _check(self, status=None, reply=None, reason=None):
		"""check_mpesa_push with Safaricom mocked: the status its answer leaves on the push (if
		any), and the reply check_transaction_status hands back."""

		def answer(name):
			if status:
				frappe.db.set_value(EXPRESS, name, {"status": status, "result_desc": reason})
			return reply

		with _at_till(), patch(CHECK, side_effect=answer) as check, patch(PULL) as pull:
			result = check_mpesa_push(self.push)
		return result, check, pull

	def test_paid_asks_for_the_receipt_from_five_minutes_before_the_push(self):
		result, _, pull = self._check(status="Completed", reply={"ResultCode": "0"})

		self.assertEqual(result, {"outcome": "paid", "transaction_id": None})
		settings, start, end = pull.call_args.args
		sent = frappe.db.get_value(EXPRESS, self.push, "creation")
		self.assertEqual(settings, self.settings)
		self.assertEqual(start, (sent - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
		self.assertGreaterEqual(end, start)

	def test_not_paid_carries_safaricom_s_reason(self):
		result, _, pull = self._check(
			status="Failed", reply={"ResultCode": "1032"}, reason="Request cancelled by user"
		)

		self.assertEqual(result, {"outcome": "not_paid", "reason": "Request cancelled by user"})
		pull.assert_not_called()

	def test_without_an_answer_the_push_stays_waiting(self):
		for reply, outcome in (
			({"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"}, "waiting"),
			({"ResultCode": "4999", "ResultDesc": "The transaction is still under processing"}, "waiting"),
			({"errorCode": "404.001.03", "errorMessage": "Invalid Access Token"}, "no_answer"),
			(None, "no_answer"),
		):
			with self.subTest(reply=reply):
				self.assertEqual(self._check(reply=reply)[0], {"outcome": outcome})
		self.assertEqual(frappe.db.get_value(EXPRESS, self.push, "status"), "In Progress")

	def test_a_push_already_answered_is_not_sent_to_safaricom(self):
		frappe.db.set_value(EXPRESS, self.push, {"status": "Completed", "transaction_id": "UJ1TEST001"})

		result, check, pull = self._check()

		self.assertEqual(result, {"outcome": "paid", "transaction_id": "UJ1TEST001"})
		check.assert_not_called()
		pull.assert_not_called()

	def test_a_second_ask_within_30_seconds_pulls_nothing(self):
		_, _, first = self._check(status="Completed", reply={"ResultCode": "0"})
		_, _, second = self._check()

		first.assert_called_once()
		second.assert_not_called()

	def test_a_cashier_may_check_ten_times_a_minute(self):
		for _ in range(10):
			self._check()

		with self.assertRaises(frappe.RateLimitExceededError):
			self._check()

	def test_only_for_a_cashier_who_may_act_on_the_order(self):
		with (
			patch.object(sales_order, "_may_act_on_held_order", return_value=False),
			self.assertRaisesRegex(frappe.ValidationError, "not allowed"),
		):
			self._check()


class TestThePushReceipt(PushCase):
	"""Safaricom said paid without a receipt number: the push is Completed, its receipt pending."""

	def setUp(self):
		super().setUp()
		frappe.db.set_value(EXPRESS, self.push, "status", "Completed")

	def _receipt(self):
		"""A register row on the push's shortcode, for its amount."""
		return make_c2b_payment(COMPANY, self.shortcode, 450, PHONE).name

	def _transid(self, register):
		return frappe.db.get_value(REGISTER, register, "transid")

	def _attach(self, register):
		"""The receipt becomes the push's, as frappe_mpsa_payments makes it."""
		frappe.db.set_value(EXPRESS, self.push, "transaction_id", self._transid(register))

	def _sale_paid_by_the_push(self, name="_Test new sale"):
		return frappe._dict(
			name=name,
			is_pos=1,
			payments=[
				frappe._dict(mode_of_payment="Mpesa-Test", amount=450, custom_reference_text=self.push)
			],
		)

	def test_a_push_paid_without_its_receipt_number_backs_the_sale(self):
		"""Safaricom's paid answer is enough: the receipt number follows when its C2B row comes in
		(frappe_mpsa_payments matches it to the push by the order number)."""
		with patch.object(mpesa, "is_mpesa_mode", return_value=True):
			mpesa.assert_mpesa_rows_backed(self._sale_paid_by_the_push())

	def test_a_push_paid_without_its_receipt_number_backs_one_sale_only(self):
		self._sold()
		with (
			patch.object(mpesa, "is_mpesa_mode", return_value=True),
			self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt"),
		):
			mpesa.assert_mpesa_rows_backed(self._sale_paid_by_the_push())

	def test_an_attached_receipt_is_not_offered_to_other_sales(self):
		"""Its order is not submitted yet, but the receipt is the push's: another till must not
		pick it."""
		receipt = self._receipt()
		transid = self._transid(receipt)

		def listed():
			found = mpesa.get_mpesa_payments(COMPANY, search=transid)["payments"]
			return [r["name"] for r in found]

		self.assertIn(receipt, listed())
		self._attach(receipt)
		self.assertNotIn(receipt, listed())

	def test_a_receipt_used_since_its_attach_stops_the_sale(self):
		"""Another till turned the attached receipt into its own Payment Entry first: this sale
		would be paid by money already spent."""
		receipt = self._receipt()
		transid = self._transid(receipt)
		self._attach(receipt)
		data = {
			"paymentMethods": [{"method": "Mpesa-Test", "amount": 450, "custom_reference_text": self.push}]
		}

		for field, used in (("payment_entry", "_Test PE used elsewhere"),):
			with self.subTest(field=field):
				frappe.db.set_value(REGISTER, receipt, field, used)
				with (
					_at_till(),
					patch.object(
						mpesa_order, "_create_invoice_draft", side_effect=AssertionError("rang up the sale")
					),
				):
					result = mpesa_order.submit_mpesa_order(self.order, data=data)
				frappe.db.set_value(REGISTER, receipt, field, None if field == "payment_entry" else 0)

				self.assertFalse(result["success"])
				self.assertEqual(result.get("code"), "mpesa_receipt_used", result)
				self.assertIn(transid, result["error"])

	def test_the_push_s_own_consumed_receipt_does_not_stop_its_sale(self):
		"""frappe_mpsa_payments submits a paid push's register row, with no Payment Entry, so it
		cannot be offered again (FAC.Allparts, 2026-10-05: SO-00368 and SO-00369 refused as
		"already used by another sale" by their own receipt)."""
		receipt = self._receipt()
		frappe.db.set_value(EXPRESS, self.push, "transaction_id", self._transid(receipt))
		frappe.db.set_value(REGISTER, receipt, {"docstatus": 1, "submit_payment": 0})
		data = {
			"paymentMethods": [{"method": "Mpesa-Test", "amount": 450, "custom_reference_text": self.push}]
		}

		self.assertIsNone(mpesa_order._receipt_used(self.push))
		with (
			_at_till(),
			patch.object(mpesa_order, "_create_invoice_draft", side_effect=RuntimeError("rang up the sale")),
		):
			result = mpesa_order.submit_mpesa_order(self.order, data=data)
		self.assertEqual(result.get("error"), "rang up the sale", result)

	def _consume(self, register):
		"""The receipt path a till with a stale search result takes: mint its Payment Entry."""
		invoice = frappe._dict(
			custom_mpesa_reconciled_payments=[
				frappe._dict(
					mpesa_c2b_payment_register=register,
					transid=self._transid(register),
					amount=450,
					mode_of_payment="Mpesa-Test",
					payment_entry=None,
				)
			]
		)
		with patch(
			"frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry.create_payment_entry",
			side_effect=AssertionError("minted a Payment Entry"),
		):
			mpesa._ensure_receipt_payment_entries(invoice)

	def _sold(self):
		"""The push's sale submitted: its invoice records the push and the push names it."""
		invoice = f"_Test SI {frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{"doctype": "Sales Invoice", "name": invoice, "docstatus": 1, "company": COMPANY}
		).db_insert()
		frappe.get_doc(
			{
				"doctype": "Sales Invoice Payment",
				"name": frappe.generate_hash(length=10),
				"parent": invoice,
				"parenttype": "Sales Invoice",
				"parentfield": "payments",
				"mode_of_payment": "Mpesa-Test",
				"amount": 450,
				"custom_reference_text": self.push,
			}
		).db_insert()
		frappe.db.set_value(
			EXPRESS, self.push, {"reference_doctype": "Sales Invoice", "reference_name": invoice}
		)
		return invoice

	def _the_push_s_receipt(self):
		receipt = self._receipt()
		self._attach(receipt)
		return receipt

	def test_a_push_s_receipt_held_for_its_order_cannot_pay_another_sale(self):
		receipt = self._the_push_s_receipt()
		with self.assertRaisesRegex(frappe.ValidationError, f"held for order {self.order}"):
			self._consume(receipt)

	def test_a_push_s_receipt_that_paid_its_sale_cannot_pay_another(self):
		receipt = self._the_push_s_receipt()
		invoice = self._sold()
		with self.assertRaisesRegex(frappe.ValidationError, f"already paid sale {invoice}"):
			self._consume(receipt)

	def test_the_push_s_sale_touches_its_receipt_row(self):
		"""A till that locked the receipt row after this sale then finds it changed and refuses."""
		receipt = self._receipt()
		self._attach(receipt)
		frappe.db.set_value(REGISTER, receipt, "modified", "2000-01-01 00:00:00", update_modified=False)

		self.assertIsNone(mpesa_order._receipt_used(self.push))

		self.assertGreater(frappe.db.get_value(REGISTER, receipt, "modified"), get_datetime("2000-01-02"))
