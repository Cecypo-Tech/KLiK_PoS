"""'Allow Closing Shift' on the POS Profile.

Off, the till's own users do not close its shift and do not see the closing figures: no
Closing Shift screen, no closing entry (from the till or the desk), no expected amounts.
A manager still closes it - someone has to - by joining the shift as today. On (the
default) nothing changes.
"""

from unittest.mock import patch

import frappe

from klik_pos.api import shift
from klik_pos.api.pos_entry import create_closing_entry, validate_closing_entry
from klik_pos.tests.test_opening_conflict import _profile, _shift
from klik_pos.tests.test_shared_shift import OPENER, SharedShiftCase

FIELD = "custom_allow_closing_shift"
CASHIER_ROLES = ["Sales User"]
MANAGER_ROLES = ["Sales Manager"]


class ClosingCase(SharedShiftCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("POS Profile", self.till, FIELD, 0)
		self.entry = _shift(self.till, OPENER)

	def _as(self, roles):
		return patch("frappe.get_roles", return_value=roles)


class TestTheSetting(ClosingCase):
	def test_a_new_till_allows_closing(self):
		self.assertTrue(shift.till_allows_closing(_profile()))

	def test_no_till_allows_closing(self):
		self.assertTrue(shift.till_allows_closing(None))

	def test_the_till_can_turn_it_off(self):
		self.assertFalse(shift.till_allows_closing(self.till))

	def test_a_cashier_may_not_close_on_it_but_a_manager_may(self):
		with self._as(CASHIER_ROLES):
			self.assertFalse(shift.may_close_on_till(self.till, OPENER))
		with self._as(MANAGER_ROLES):
			self.assertTrue(shift.may_close_on_till(self.till, OPENER))


class TestClosingIsRefused(ClosingCase):
	def test_from_the_till(self):
		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES), patch(
			"klik_pos.api.pos_entry._parse_request_data", return_value={"closing_balance": {}}
		):
			with self.assertRaisesRegex(frappe.PermissionError, "Closing is turned off"):
				create_closing_entry()

	def test_from_the_desk(self):
		closing = frappe.new_doc("POS Closing Entry")
		closing.pos_opening_entry = self.entry
		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES):
			with self.assertRaisesRegex(frappe.PermissionError, "Closing is turned off"):
				validate_closing_entry(closing, "validate")

	def test_but_a_manager_may_close_it(self):
		closing = frappe.new_doc("POS Closing Entry")
		closing.pos_opening_entry = self.entry
		frappe.set_user(OPENER)
		with self._as(MANAGER_ROLES):
			validate_closing_entry(closing, "validate")

	def test_and_a_till_that_allows_it_is_unchanged(self):
		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		closing = frappe.new_doc("POS Closing Entry")
		closing.pos_opening_entry = self.entry
		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES):
			validate_closing_entry(closing, "validate")


class TestTheFiguresStayPrivate(ClosingCase):
	def _summary(self, roles):
		from klik_pos.api import payment

		sales = [{"mode_of_payment": "Cash", "total_amount": 500.0, "transactions": 3}]
		frappe.set_user(OPENER)
		with (
			self._as(roles),
			patch.object(payment, "get_current_pos_opening_entry", return_value=self.entry),
			patch.object(payment, "_fetch_opening_sales_data", return_value=sales),
			# A Sales Manager gets the admin view, the till's day.
			patch.object(payment, "_fetch_daily_sales_data", return_value=sales),
		):
			return payment.get_opening_entry_payment_summary()

	def test_the_payment_summary_keeps_the_modes_but_not_the_amounts(self):
		"""Invoice History filters by these modes; the amounts are the closing figures."""
		summary = self._summary(CASHIER_ROLES)
		self.assertTrue(summary["success"])
		self.assertTrue(summary["figures_hidden"])
		self.assertEqual([m["name"] for m in summary["data"]], ["Cash"])
		self.assertEqual(
			{(m["amount"], m["openingAmount"], m["transactions"]) for m in summary["data"]}, {(0.0, 0.0, 0)}
		)

	def test_a_manager_sees_them(self):
		summary = self._summary(MANAGER_ROLES)
		self.assertFalse(summary.get("figures_hidden"))
		self.assertEqual(summary["data"][0]["amount"], 500.0)

	def test_the_closing_invoice_list_is_refused(self):
		from klik_pos.api.sales_invoice import get_sales_invoices

		till_doc = frappe.get_doc("POS Profile", self.till)
		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES), patch(
			"klik_pos.api.sales_invoice.get_current_pos_profile", return_value=till_doc
		):
			result = get_sales_invoices(surface="")
			self.assertFalse(result["success"])
			self.assertIn("Closing is turned off", result["error"])
			# Any surface other than the three named screens gets the closing scope.
			self.assertFalse(get_sales_invoices(surface="anything")["success"])
			# Invoice History is another screen and is unaffected.
			self.assertTrue(get_sales_invoices(surface="history")["success"])

	def test_the_user_info_tells_the_till_whether_to_offer_closing(self):
		from klik_pos.api.user import get_current_user_info

		till_doc = frappe.get_doc("POS Profile", self.till)
		frappe.set_user(OPENER)
		with patch("klik_pos.klik_pos.utils.get_current_pos_profile", return_value=till_doc):
			with self._as(CASHIER_ROLES):
				self.assertFalse(get_current_user_info()["data"]["can_close_shift"])
			with self._as(MANAGER_ROLES):
				self.assertTrue(get_current_user_info()["data"]["can_close_shift"])


class TestAStaleShiftWaitsForAManager(ClosingCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("POS Opening Entry", self.entry, "status", "Closed")
		self.entry = _shift(self.till, OPENER, days_ago=1)

	def test_the_till_is_told_not_to_send_the_cashier_to_closing(self):
		from klik_pos.api.pos_entry import current_shift_state, opening_conflict

		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES):
			state = current_shift_state()
			self.assertEqual((state["stale"], state["can_close"]), (True, False))
			conflict = opening_conflict(self.till)
			self.assertEqual((conflict["kind"], conflict["can_close"]), ("own_stale", False))
		with self._as(MANAGER_ROLES):
			self.assertTrue(current_shift_state()["can_close"])


class TestTheDeskAndTheManager(ClosingCase):
	def test_get_entries_on_the_desk_form_is_refused(self):
		from klik_pos.overrides.pos_closing_entry import get_invoices

		frappe.set_user(OPENER)
		with self._as(CASHIER_ROLES):
			with self.assertRaisesRegex(frappe.PermissionError, "Closing is turned off"):
				get_invoices(frappe.utils.add_days(frappe.utils.now(), -1), frappe.utils.now(), self.till, OPENER)

	def test_a_manager_joins_the_till_s_shift_and_may_close_it(self):
		from klik_pos.tests.test_opening_conflict import _user
		from klik_pos.tests.test_shared_shift import _assign

		manager = _user("closing-off-manager@example.com")
		_assign(self.till, manager)
		frappe.set_user(manager)
		with self._as(MANAGER_ROLES):
			self.assertEqual(shift.join_shift(self.till)["entry"], self.entry)
			closing = frappe.new_doc("POS Closing Entry")
			closing.pos_opening_entry = self.entry
			validate_closing_entry(closing, "validate")

	def test_the_opening_screen_keeps_the_last_count_from_the_till(self):
		from klik_pos.api.opening_balances import opening_suggestion

		last = {"Cash": {"amount": 1000.0, "counted": 1200.0, "banked": 200.0, "closing_entry": "X", "closed_on": None}}
		with (
			patch("klik_pos.api.opening_balances.last_closing", return_value=last),
			patch("frappe.has_permission", return_value=True),
		):
			frappe.set_user(OPENER)
			with self._as(CASHIER_ROLES):
				cash = next(m for m in opening_suggestion(self.till)["modes"] if m["mode_of_payment"] == "Cash")
			self.assertEqual(cash["suggested_amount"], 1000.0)
			self.assertEqual((cash["previous_counted_amount"], cash["previous_banked_amount"]), (0.0, 0.0))
			with self._as(MANAGER_ROLES):
				cash = next(m for m in opening_suggestion(self.till)["modes"] if m["mode_of_payment"] == "Cash")
			self.assertEqual((cash["previous_counted_amount"], cash["previous_banked_amount"]), (1200.0, 200.0))
