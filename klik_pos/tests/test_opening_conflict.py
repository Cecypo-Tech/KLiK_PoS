"""What stands in the way of a cashier opening a till, and what the opening screen offers.

A cashier may hold one open shift at a time (validate_opening_entry). The opening screen
used to find out about an existing one only when create failed, as raw JSON, and then
treated the failure as a success and reopened itself. opening_conflict names the shift in
the way so the screen can send the cashier into it or to the closing screen.

"Open" means status Open - the rule open_pos, the closing screen and ERPNext itself use.
create_opening_entry had its own rule, "no closing entry linked", so a shift set to Closed
without one (a test suite retiring stale shifts did exactly that) was open to create and
closed to everything else: the screen appeared, and opening from it always failed.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import pos_entry
from klik_pos.api.pos_entry import opening_conflict

COMPANY = "Dev Co"
CASHIER = "opening-conflict-cashier@example.com"
OTHER = "opening-conflict-other@example.com"


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


def _profile():
	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": f"_Test Opening Conflict {frappe.generate_hash(length=6)}",
			"company": COMPANY,
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
			"warehouse": frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name"),
			"payments": [{"mode_of_payment": "Cash", "default": 1}],
		}
	)
	profile.insert(ignore_permissions=True, ignore_mandatory=True)
	return profile.name


def _shift(profile, user, status="Open", days_ago=0, closing_entry=None):
	"""A submitted POS Opening Entry, written past validation: the rules under test are
	about reading shifts, not about which ones ERPNext would let exist."""
	doc = frappe.new_doc("POS Opening Entry")
	doc.pos_profile = profile
	doc.company = COMPANY
	doc.user = user
	doc.period_start_date = frappe.utils.add_to_date(None, days=-days_ago)
	doc.posting_date = frappe.utils.add_days(frappe.utils.nowdate(), -days_ago)
	doc.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value(
		"POS Opening Entry",
		doc.name,
		{"docstatus": 1, "status": status, "pos_closing_entry": closing_entry},
		update_modified=False,
	)
	return doc.name


class OpeningConflictCase(FrappeTestCase):
	def setUp(self):
		_user(CASHIER)
		_user(OTHER)
		self.profile = _profile()
		self.other_profile = _profile()
		frappe.set_user(CASHIER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestOpeningConflict(OpeningConflictCase):
	def test_nothing_open_is_no_conflict(self):
		self.assertIsNone(opening_conflict(self.profile))

	def test_own_shift_on_this_profile_today_can_be_continued(self):
		entry = _shift(self.profile, CASHIER)

		conflict = opening_conflict(self.profile)

		self.assertEqual(conflict["kind"], "own_open")
		self.assertEqual(conflict["entry"], entry)
		self.assertEqual(conflict["pos_profile"], self.profile)

	def test_own_shift_from_an_earlier_day_must_be_closed(self):
		entry = _shift(self.profile, CASHIER, days_ago=1)

		conflict = opening_conflict(self.profile)

		self.assertEqual(conflict["kind"], "own_stale")
		self.assertEqual(conflict["entry"], entry)

	def test_own_shift_on_another_profile_must_be_closed(self):
		entry = _shift(self.other_profile, CASHIER)

		conflict = opening_conflict(self.profile)

		self.assertEqual(conflict["kind"], "own_other_profile")
		self.assertEqual(conflict["entry"], entry)
		self.assertEqual(conflict["pos_profile"], self.other_profile)

	def test_another_cashier_on_the_same_profile_is_no_conflict(self):
		"""klik_pos lets several cashiers share a till; only your own shift is in the way."""
		_shift(self.profile, OTHER)

		self.assertIsNone(opening_conflict(self.profile))

	def test_a_shift_closed_without_a_closing_entry_is_no_conflict(self):
		_shift(self.profile, CASHIER, status="Closed", closing_entry=None)

		self.assertIsNone(opening_conflict(self.profile))


class TestCreateOpeningEntryUsesTheSameRule(OpeningConflictCase):
	def _create(self):
		frappe.local.form_dict = frappe._dict(
			pos_profile=self.profile,
			opening_balance=[{"mode_of_payment": "Cash", "opening_amount": 0}],
		)
		new_doc = MagicMock()
		new_doc.return_value.name = "POS-OPE-FAKE"
		with (
			patch.object(pos_entry.frappe.defaults, "get_user_default", return_value=COMPANY),
			patch.object(pos_entry.frappe, "new_doc", new_doc),
			patch.object(pos_entry, "clear_pos_profile_cache"),
		):
			return pos_entry.create_opening_entry()

	def test_regression_closed_without_closing_entry_does_not_block_opening(self):
		_shift(self.profile, CASHIER, status="Closed", closing_entry=None)

		self.assertEqual(self._create()["name"], "POS-OPE-FAKE")

	def test_own_open_shift_blocks_opening_with_one_readable_message(self):
		entry = _shift(self.profile, CASHIER, days_ago=1)
		frappe.clear_messages()

		with self.assertRaises(frappe.ValidationError) as raised:
			self._create()

		self.assertIn(entry, str(raised.exception))
		self.assertNotIn("Failed to create", str(raised.exception))
		self.assertEqual(len(frappe.local.message_log), 1)
