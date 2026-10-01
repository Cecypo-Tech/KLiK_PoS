"""'Require Daily Shift Close' on the POS Profile.

On (the default) a till's shift is good for the day it was opened, ERPNext's rule: the next
day it is stale, sales are refused, and it must be closed. Off, a till's open shift is good
until someone closes it - how klik worked before it stopped overriding ERPNext's check -
so closing is when the money is counted, not a daily chore.
"""

from unittest.mock import patch

import frappe

from klik_pos.api import shift
from klik_pos.api.pos_entry import (
	_ensure_may_close,
	current_shift_state,
	opening_conflict,
	validate_closing_entry,
)
from klik_pos.tests.test_opening_conflict import COMPANY, _profile, _shift
from klik_pos.tests.test_shared_shift import JOINER, OPENER, SharedShiftCase

FIELD = "custom_require_daily_shift_close"


class DailyCloseCase(SharedShiftCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("POS Profile", self.till, FIELD, 0)


class TestTheSetting(DailyCloseCase):
	def test_a_new_till_requires_a_daily_close(self):
		self.assertTrue(shift.requires_daily_close(_profile()))

	def test_no_till_means_erpnext_s_daily_rule(self):
		self.assertTrue(shift.requires_daily_close(None))
		self.assertTrue(shift.requires_daily_close("No Such Till"))

	def test_the_till_can_turn_it_off(self):
		self.assertFalse(shift.requires_daily_close(self.till))


class TestAShiftFromAnEarlierDay(DailyCloseCase):
	def test_is_not_stale_on_a_till_without_a_daily_close(self):
		entry = _shift(self.till, OPENER, days_ago=3)
		row = frappe.db.get_value("POS Opening Entry", entry, ["name", "period_start_date"], as_dict=True)
		self.assertFalse(shift._is_stale(row))

	def test_is_still_stale_on_a_till_with_a_daily_close(self):
		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		entry = _shift(self.till, OPENER, days_ago=1)
		row = frappe.db.get_value("POS Opening Entry", entry, ["name", "period_start_date"], as_dict=True)
		self.assertTrue(shift._is_stale(row))

	def test_the_cashier_carries_on_selling_in_it(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		self.assertEqual(current_shift_state()["stale"], False)
		self.assertEqual(current_shift_state()["entry"], entry)
		self.assertEqual(opening_conflict(self.till)["kind"], "own_open")

	def test_another_cashier_joins_it_without_a_manager(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)
		self.assertEqual(opening_conflict(self.till)["kind"], "till_open")
		self.assertEqual(shift.join_shift(self.till)["entry"], entry)
		self.assertEqual(shift.joined_shift(JOINER), entry)

	def test_a_cashier_who_joined_it_may_close_it(self):
		entry = _shift(self.till, OPENER, days_ago=2)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		row = frappe.db.get_value(
			"POS Opening Entry", entry, ["name", "user", "pos_profile", "period_start_date"], as_dict=True
		)
		with patch("frappe.get_roles", return_value=["Sales User"]):
			_ensure_may_close(row, JOINER)
			# The desk's POS Closing Entry is held to the same rule.
			closing = frappe.new_doc("POS Closing Entry")
			closing.pos_opening_entry = entry
			validate_closing_entry(closing, "validate")

	def test_turning_the_setting_back_on_makes_it_stale_at_once(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		self.assertFalse(current_shift_state()["stale"])
		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		self.assertEqual(current_shift_state(), {**current_shift_state(), "entry": entry, "stale": True})

	def test_two_open_shifts_on_the_till_still_need_a_manager(self):
		_shift(self.till, OPENER, days_ago=1)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)
		self.assertEqual(opening_conflict(self.till)["kind"], "till_needs_manager")


class TestASaleOnIt(DailyCloseCase):
	def _invoice(self):
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": COMPANY,
				"pos_profile": self.till,
				"is_pos": 1,
				"custom_is_created_from_klik": 1,
			}
		)
		return doc

	def _before_submit(self, doc):
		with (
			patch.object(type(doc), "validate_reserved_stock_availability"),
			patch.object(type(doc), "validate_full_payment"),
			patch("klik_pos.api.sales_invoice._should_reserve_stock", return_value=False),
		):
			doc.before_submit()

	def test_goes_through_on_a_till_without_a_daily_close(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		self._before_submit(self._invoice())

	def test_is_refused_on_a_till_with_a_daily_close(self):
		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		with self.assertRaisesRegex(frappe.ValidationError, "outdated"):
			self._before_submit(self._invoice())

	def test_still_needs_an_open_shift(self):
		frappe.set_user(OPENER)
		with self.assertRaisesRegex(frappe.ValidationError, "No open POS Opening Entry"):
			self._before_submit(self._invoice())

	def test_still_needs_exactly_one_open_shift(self):
		_shift(self.till, OPENER, days_ago=1)
		_shift(self.till, JOINER)
		frappe.set_user(OPENER)
		with self.assertRaisesRegex(frappe.ValidationError, "multiple open"):
			self._before_submit(self._invoice())


class TestTheDashboard(DailyCloseCase):
	def _count(self):
		from klik_pos.api.dashboard import _exceptions

		rows = _exceptions(COMPANY, {"available_profiles": [self.till]}, [])
		return {row["key"]: row["count"] for row in rows}.get("shifts_open_past_today", 0)

	def test_a_long_shift_on_a_till_without_a_daily_close_is_not_an_exception(self):
		before = self._count()
		_shift(self.till, OPENER, days_ago=2)
		self.assertEqual(self._count(), before)

	def test_a_forgotten_shift_on_a_till_with_a_daily_close_still_is(self):
		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		before = self._count()
		_shift(self.till, OPENER, days_ago=2)
		self.assertEqual(self._count(), before + 1)


class TestThePaymentSummary(DailyCloseCase):
	def test_an_admin_closing_a_long_shift_sees_the_whole_shift(self):
		"""The admin view sums the till's sales on the shift's first day. A shift that runs
		for days on a till without a daily close would show only that first day."""
		from klik_pos.api import payment

		entry = _shift(self.till, OPENER, days_ago=2)
		with (
			patch.object(payment, "get_current_pos_opening_entry", return_value=entry),
			patch.object(payment, "_check_admin_privileges", return_value=True),
			patch.object(payment, "_fetch_opening_sales_data", return_value=[]) as by_shift,
			patch.object(payment, "_fetch_daily_sales_data", return_value=[]) as by_day,
		):
			payment.get_opening_entry_payment_summary()
		by_shift.assert_called_once_with(entry)
		by_day.assert_not_called()

	def test_an_admin_on_a_daily_till_still_sees_the_day(self):
		from klik_pos.api import payment

		frappe.db.set_value("POS Profile", self.till, FIELD, 1)
		entry = _shift(self.till, OPENER)
		with (
			patch.object(payment, "get_current_pos_opening_entry", return_value=entry),
			patch.object(payment, "_check_admin_privileges", return_value=True),
			patch.object(payment, "_fetch_opening_sales_data", return_value=[]) as by_shift,
			patch.object(payment, "_fetch_daily_sales_data", return_value=[]) as by_day,
		):
			payment.get_opening_entry_payment_summary()
		by_day.assert_called_once()
		by_shift.assert_not_called()
