"""One shift per till, joined by every cashier on it.

Each cashier used to open their own POS Opening Entry, even on a shared till, and the close
then counted the whole till's sales for each of them. A till now runs one shift: the first
cashier opens it, the others join it, and whoever closes it closes it for everyone.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import shift
from klik_pos.api.pos_entry import open_pos
from klik_pos.api.sales_invoice import get_current_pos_opening_entry
from klik_pos.tests.test_opening_conflict import COMPANY, _profile, _shift, _user

OPENER = "shared-shift-opener@example.com"
JOINER = "shared-shift-joiner@example.com"


def _assign(profile, *users):
	doc = frappe.get_doc("POS Profile", profile)
	for user in users:
		doc.append("applicable_for_users", {"user": user})
	# The fixture profile was inserted with ignore_mandatory; saving it must skip the same checks.
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


class SharedShiftCase(FrappeTestCase):
	def setUp(self):
		_user(OPENER)
		_user(JOINER)
		self.till = _profile()
		_assign(self.till, OPENER, JOINER)
		frappe.defaults.clear_user_default(shift.JOINED_SHIFT_KEY, JOINER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestJoining(SharedShiftCase):
	def test_a_cashier_on_the_till_joins_its_open_shift(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		self.assertEqual(shift.join_shift(self.till), {"success": True, "entry": entry})
		self.assertEqual(get_current_pos_opening_entry(), entry)
		self.assertTrue(open_pos())

	def test_a_cashier_not_on_the_till_cannot_join(self):
		_shift(self.till, OPENER)
		outsider = _user("shared-shift-outsider@example.com")
		frappe.set_user(outsider)

		with self.assertRaises(frappe.PermissionError):
			shift.join_shift(self.till)

	def test_there_is_nothing_to_join_on_a_closed_till(self):
		frappe.set_user(JOINER)
		with self.assertRaises(frappe.ValidationError):
			shift.join_shift(self.till)

	def test_a_joined_shift_that_has_closed_is_forgotten(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		frappe.db.set_value("POS Opening Entry", entry, "status", "Closed")

		self.assertIsNone(get_current_pos_opening_entry())
		self.assertFalse(open_pos())

	def test_my_own_open_shift_wins_over_a_joined_one(self):
		other_till = _profile()
		_assign(other_till, JOINER)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		mine = _shift(other_till, JOINER)

		self.assertEqual(get_current_pos_opening_entry(), mine)
