"""An STK push whose confirmation never arrived: "Check with M-Pesa" asks Safaricom, and when it
says paid - an answer with no receipt number - the receipt is found in the register and attached,
so the sale submits like any confirmed push.

Safaricom is never called: check_transaction_status and pull_transactions are mocked (dev's
sandbox shortcode cannot use the Pull API either).
"""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.mpesa_order import check_mpesa_push
from klik_pos.tests.test_held_order_orphans import COMPANY
from klik_pos.tests.test_mpesa_order_checkout import _at_till, _order

EXPRESS = "Mpesa Express Request"
PHONE = "254700000123"
CHECK = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.check_transaction_status"
PULL = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.pull_transactions"


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
