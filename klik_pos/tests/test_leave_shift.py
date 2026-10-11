"""A cashier who joined a till's shift can step out of it to work on another of their
profiles - say, one that allows returns. The shift stays open for the till; only the cashier
who opened it can't leave it, because a shift with no owner in it could never be closed."""

import frappe

from klik_pos.api import shift
from klik_pos.api.pos_entry import current_shift_state
from klik_pos.api.sales_invoice import get_current_pos_opening_entry
from klik_pos.tests.test_opening_conflict import _shift
from klik_pos.tests.test_shared_shift import JOINER, OPENER, SharedShiftCase


class TestLeavingAShift(SharedShiftCase):
	def test_a_cashier_who_joined_leaves_and_the_shift_stays_open(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		self.assertEqual(shift.leave_shift(), {"success": True})
		self.assertIsNone(get_current_pos_opening_entry())
		self.assertEqual(frappe.db.get_value("POS Opening Entry", entry, "status"), "Open")

	def test_the_cashier_who_opened_the_shift_cannot_leave_it(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(OPENER)

		with self.assertRaises(frappe.ValidationError):
			shift.leave_shift()
		self.assertEqual(get_current_pos_opening_entry(), entry)

	def test_leaving_with_no_shift_does_nothing(self):
		frappe.set_user(JOINER)
		self.assertEqual(shift.leave_shift(), {"success": True})


class TestTheShiftStateSaysWhoseShiftItIs(SharedShiftCase):
	def test_a_joined_shift_names_its_opener(self):
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		state = current_shift_state()
		self.assertTrue(state["joined"])
		self.assertEqual(state["opened_by"], OPENER)
		self.assertEqual(state["opened_by_name"], frappe.db.get_value("User", OPENER, "full_name"))

	def test_my_own_shift_is_not_joined(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)

		state = current_shift_state()
		self.assertFalse(state["joined"])
		self.assertEqual(state["opened_by"], OPENER)
