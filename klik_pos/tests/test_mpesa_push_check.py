"""An STK push whose confirmation never arrived: "Check with M-Pesa" asks Safaricom, and when it
says paid - an answer with no receipt number - the receipt is found in the register and attached,
so the sale submits like any confirmed push.

Safaricom is never called: check_transaction_status and pull_transactions are mocked (dev's
sandbox shortcode cannot use the Pull API either).
"""

from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_system_timezone, now_datetime

from klik_pos.api import mpesa, mpesa_order, sales_order
from klik_pos.api.mpesa_order import attach_push_receipt, check_mpesa_push, find_push_receipts
from klik_pos.tests.mpesa_fixtures import make_c2b_payment
from klik_pos.tests.test_held_order_orphans import COMPANY
from klik_pos.tests.test_mpesa_order_checkout import _at_till, _order

EXPRESS = "Mpesa Express Request"
PHONE = "254700000123"
CHECK = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.check_transaction_status"
PULL = "frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api.pull_transactions"
REGISTER = "Mpesa C2B Payment Register"


def _safaricom_time(minutes, offset=True):
	"""Safaricom's time `minutes` from now: as a pulled row carries it (ISO, with its offset), or as
	a webhook or statement row does (East Africa Time, no offset)."""
	at = (now_datetime() + timedelta(minutes=minutes)).replace(tzinfo=ZoneInfo(get_system_timezone()))
	return at.isoformat() if offset else at.astimezone(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H%M%S")


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

	def _receipt(self, amount=450, msisdn=PHONE, billref=None, transtime=None):
		"""A register row on the push's shortcode; with no readable transtime it counts from when
		it was stored (just now, after the push)."""
		row = make_c2b_payment(COMPANY, self.shortcode, amount, msisdn, billrefnumber=billref)
		if transtime:
			frappe.db.set_value(REGISTER, row.name, "transtime", transtime)
		return row.name

	def _transid(self, register):
		return frappe.db.get_value(REGISTER, register, "transid")

	def _find(self, pull=0):
		with _at_till(), patch(PULL) as pull_mock:
			return find_push_receipts(self.push, pull=pull), pull_mock

	def _attach(self, register):
		with _at_till():
			return attach_push_receipt(self.push, register)

	def test_lists_the_receipts_that_can_be_the_push_s(self):
		# East Africa Time with no offset: on a site in another zone (dev runs Asia/Kolkata) a naive
		# comparison would put this receipt hours before the push.
		full = self._receipt(transtime=_safaricom_time(1, offset=False))
		masked = self._receipt(msisdn="25470****123", transtime=_safaricom_time(1))
		by_order = self._receipt(msisdn="254711111111", billref=self.order)
		self._receipt(amount=400)
		self._receipt(msisdn="254711111111")
		self._receipt(transtime=_safaricom_time(-10))
		taken = self._receipt()
		self._push(status="Completed", transaction_id=self._transid(taken))
		used = self._receipt()
		frappe.db.set_value(REGISTER, used, "docstatus", 1)

		found, pull = self._find()

		self.assertIsNone(found["transaction_id"])
		self.assertCountEqual([r.name for r in found["receipts"]], [full, masked, by_order])
		pull.assert_not_called()

	def test_the_lookup_asks_for_a_pull_when_told(self):
		_, pull = self._find(pull=1)

		pull.assert_called_once()

	def test_a_masked_phone_matches_on_the_digits_it_shows(self):
		for msisdn, same in (
			("254700000123", True),
			("+254 700 000 123", True),
			("25470****123", True),
			("2547 ***** 123", True),
			("25471****123", False),
			("254*********", False),
			("254711111111", False),
			("", False),
			# A hashed number (C2B v2) shows no phone at all.
			("54f65df3bfa35fabd44ff4249b6b9eaf2bb1168c1f55fc205812a27676e1a19d", False),
		):
			with self.subTest(msisdn=msisdn):
				self.assertEqual(mpesa_order._same_payer(msisdn, PHONE), same)

	def test_the_attached_receipt_becomes_the_push_s(self):
		receipt = self._receipt()
		transid = self._transid(receipt)

		self.assertEqual(self._attach(receipt), {"transaction_id": transid})

		self.assertEqual(frappe.db.get_value(EXPRESS, self.push, "transaction_id"), transid)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": EXPRESS,
					"reference_name": self.push,
					"comment_email": frappe.session.user,
					"content": ["like", f"%{transid}%"],
				},
			)
		)
		found, _ = self._find()
		self.assertEqual((found["transaction_id"], found["receipts"]), (transid, []))

	def test_an_attached_receipt_backs_the_sale(self):
		"""The M-Pesa row the till sends for a confirmed push: refused before, accepted after."""
		invoice = frappe._dict(
			name="_Test new sale",
			is_pos=1,
			payments=[
				frappe._dict(mode_of_payment="Mpesa-Test", amount=450, custom_reference_text=self.push)
			],
		)
		with patch.object(mpesa, "is_mpesa_mode", return_value=True):
			with self.assertRaisesRegex(frappe.ValidationError, "no M-Pesa receipt"):
				mpesa.assert_mpesa_rows_backed(invoice)
			self._attach(self._receipt())
			mpesa.assert_mpesa_rows_backed(invoice)

	def test_attaching_refuses_a_receipt_that_cannot_be_the_push_s(self):
		taken = self._receipt()
		self._push(status="Completed", transaction_id=self._transid(taken))
		used = self._receipt()
		frappe.db.set_value(REGISTER, used, "docstatus", 1)
		refusals = {
			"not 450": self._receipt(amount=400),
			"another phone": self._receipt(msisdn="254711111111"),
			"another M-Pesa number": make_c2b_payment(COMPANY, f"{self.shortcode}9", 450, PHONE).name,
			"before the M-Pesa request": self._receipt(transtime=_safaricom_time(-10)),
			"used by a sale": used,
			"already M-Pesa request": taken,
		}

		for reason, receipt in refusals.items():
			with self.subTest(reason=reason), self.assertRaisesRegex(frappe.ValidationError, reason):
				self._attach(receipt)
		self.assertIsNone(frappe.db.get_value(EXPRESS, self.push, "transaction_id"))

	def test_a_push_confirmed_meanwhile_takes_no_other_receipt(self):
		"""Safaricom's own confirmation came after the check: its receipt number stands."""
		frappe.db.set_value(EXPRESS, self.push, "transaction_id", "UJ1LATE001")

		with self.assertRaisesRegex(frappe.ValidationError, "not waiting for its receipt"):
			self._attach(self._receipt())

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

		for field, used in (("docstatus", 1), ("payment_entry", "_Test PE used elsewhere")):
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
