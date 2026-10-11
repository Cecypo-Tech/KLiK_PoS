"""Switch profile: a cashier steps out of the shift they are in - one they joined or one
they opened - to work on another of their profiles, say one that allows returns. The shift
stays open: anyone still in it, or a manager, closes it. A cashier may hold an open shift on
one till while they work on another; a till still runs one shift at a time."""

import frappe

from klik_pos.api import shift
from klik_pos.api.pos_entry import current_shift_state, opening_conflict, remember_opened_shift
from klik_pos.api.sales_invoice import get_current_pos_opening_entry
from klik_pos.tests.test_opening_conflict import _profile, _shift
from klik_pos.tests.test_shared_shift import JOINER, OPENER, SharedShiftCase, _assign


class TestLeavingAShift(SharedShiftCase):
	def test_a_cashier_who_joined_leaves_and_the_shift_stays_open(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		self.assertEqual(shift.leave_shift(), {"success": True})
		self.assertIsNone(get_current_pos_opening_entry())
		self.assertEqual(frappe.db.get_value("POS Opening Entry", entry, "status"), "Open")

	def test_the_opener_leaves_and_whoever_joined_stays_in_it(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		frappe.set_user(OPENER)

		self.assertEqual(shift.leave_shift(), {"success": True})
		self.assertIsNone(get_current_pos_opening_entry())
		self.assertEqual(frappe.db.get_value("POS Opening Entry", entry, "status"), "Open")
		frappe.set_user(JOINER)
		self.assertEqual(get_current_pos_opening_entry(), entry)

	def test_leaving_with_no_shift_does_nothing(self):
		frappe.set_user(JOINER)
		self.assertEqual(shift.leave_shift(), {"success": True})


class TestWorkingOnAnotherTill(SharedShiftCase):
	def setUp(self):
		super().setUp()
		self.other_till = _profile()
		_assign(self.other_till, OPENER)
		self.left = _shift(self.till, OPENER)
		frappe.set_user(OPENER)
		shift.leave_shift()

	def test_the_other_till_has_nothing_in_the_way(self):
		self.assertIsNone(opening_conflict(self.other_till))

	def test_neither_klik_nor_erpnext_refuses_a_second_open_shift_on_another_till(self):
		from unittest.mock import patch

		from klik_pos.api.pos_entry import validate_opening_entry

		doc = frappe.new_doc("POS Opening Entry")
		doc.update({"pos_profile": self.other_till, "user": OPENER})
		doc.check_user_already_assigned()  # ERPNext's one-shift-per-cashier rule, overridden
		with patch("klik_pos.api.opening_balances.enforce"):
			validate_opening_entry(doc, None)

	def test_the_shift_opened_there_is_the_one_worked_in(self):
		new = _shift(self.other_till, OPENER)
		remember_opened_shift(frappe.get_doc("POS Opening Entry", new))

		self.assertEqual(get_current_pos_opening_entry(), new)

	def test_opening_a_shift_is_remembered_on_submit(self):
		self.assertIn(
			"klik_pos.api.pos_entry.remember_opened_shift",
			frappe.get_hooks("doc_events")["POS Opening Entry"]["on_submit"],
		)

	def test_coming_back_to_the_left_till_takes_the_cashier_back_into_their_shift(self):
		self.assertEqual(opening_conflict(self.till)["kind"], "own_open")
		shift.join_shift(self.till)
		self.assertEqual(get_current_pos_opening_entry(), self.left)

	def test_a_stale_shift_of_one_s_own_can_be_re_entered_to_close_it(self):
		frappe.db.set_value("POS Opening Entry", self.left, "period_start_date",
			frappe.utils.add_to_date(None, days=-1))
		from unittest.mock import patch

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(opening_conflict(self.till)["kind"], "own_stale")
			shift.join_shift(self.till)
			self.assertEqual(get_current_pos_opening_entry(), self.left)


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
