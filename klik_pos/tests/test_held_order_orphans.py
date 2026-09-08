"""Held orders must not be able to outlive every shift that could clean them up.

A held order is stamped with the opening entry that was current when it was held - and with
an empty one when no shift was open, because that is what get_current_pos_opening_entry
returns then. The close sweep matched on that stamp, so an unstamped order was swept by
nothing: it sat in the Draft tab for good. Worse, _assert_held_order_access tied access to
the caller's current opening entry, so the cashier who found it could neither serve it nor
clear it - only a System Manager could act at all.

Both halves are fixed here: the close sweeps orphans on its own till, and a cashier may act
on one stranded on the till they are standing at.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.sales_order import _assert_held_order_access, delete_held_orders_for_opening_entry

COMPANY = "Dev Co"
PROFILE = "_Test POS Profile"
ITEM = "Consulting"
CUSTOMER = "Walk In"


def _opening_entry(status="Open", hours_ago=2):
	"""A POS Opening Entry standing in for a shift.

	Validation is skipped deliberately: ERPNext refuses a second open entry for the same
	cashier and till, and a dev site usually has one already. These tests are about which
	held orders a close sweeps, not about ERPNext's own shift rules, and the sweep reads
	only pos_profile, period_start_date and status.
	"""
	doc = frappe.new_doc("POS Opening Entry")
	doc.pos_profile = PROFILE
	doc.company = COMPANY
	doc.user = frappe.session.user
	doc.period_start_date = frappe.utils.add_to_date(None, hours=-hours_ago)
	doc.posting_date = frappe.utils.nowdate()
	doc.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.set_value(
		"POS Opening Entry", doc.name, {"docstatus": 1, "status": status}, update_modified=False
	)
	doc.reload()
	return doc


def _held_order(opening_entry="", profile=PROFILE, minutes_ago=60, owner=None):
	so = frappe.new_doc("Sales Order")
	so.customer = CUSTOMER
	so.company = COMPANY
	so.transaction_date = frappe.utils.nowdate()
	so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 1)
	so.append("items", {"item_code": ITEM, "qty": 1, "rate": 10, "delivery_date": so.delivery_date})
	so.insert(ignore_permissions=True)
	values = {
		"custom_is_klik_held": 1,
		"custom_pos_profile": profile,
		"custom_pos_opening_entry": opening_entry,
		"modified": frappe.utils.add_to_date(None, minutes=-minutes_ago),
	}
	if owner:
		values["owner"] = owner
	frappe.db.set_value("Sales Order", so.name, values, update_modified=False)
	so.reload()
	return so


def _exists(so):
	return bool(frappe.db.exists("Sales Order", so.name))


class TestClosingSweepsOrphans(FrappeTestCase):
	def test_an_order_held_with_no_shift_open_is_swept(self):
		"""The regression: nothing ever deleted these, so they accumulated forever."""
		closing = _opening_entry(hours_ago=2)
		# Held four hours ago, while nothing was open - so it predates the shift now closing.
		orphan = _held_order(opening_entry="", minutes_ago=240)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertFalse(_exists(orphan))

	def test_an_order_stranded_on_an_already_closed_shift_is_swept(self):
		earlier = _opening_entry(status="Closed", hours_ago=6)
		stranded = _held_order(opening_entry=earlier.name, minutes_ago=300)
		closing = _opening_entry(hours_ago=2)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertFalse(_exists(stranded))

	def test_this_session_s_own_held_orders_are_still_swept(self):
		closing = _opening_entry()
		mine = _held_order(opening_entry=closing.name, minutes_ago=0)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertFalse(_exists(mine))

	def test_an_orphan_on_another_till_is_left_alone(self):
		"""Closing one counter must not clear another counter's work."""
		closing = _opening_entry(hours_ago=2)
		other_till = _held_order(opening_entry="", profile="SOME-OTHER-TILL", minutes_ago=240)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertTrue(_exists(other_till))

	def test_an_orphan_newer_than_this_shift_is_left_alone(self):
		"""Held after this shift opened means it belongs to a session this close cannot see."""
		closing = _opening_entry(hours_ago=2)
		newer = _held_order(opening_entry="", minutes_ago=0)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertTrue(_exists(newer))

	def test_an_order_on_another_open_shift_is_left_alone(self):
		live = _opening_entry(hours_ago=6)
		other_session = _held_order(opening_entry=live.name, minutes_ago=300)
		closing = _opening_entry(hours_ago=2)

		delete_held_orders_for_opening_entry(closing.name)

		self.assertTrue(_exists(other_session))

	def test_an_unknown_opening_entry_sweeps_nothing_rather_than_everything(self):
		orphan = _held_order(opening_entry="", minutes_ago=240)

		deleted = delete_held_orders_for_opening_entry("POS-OPE-DOES-NOT-EXIST")

		self.assertEqual(deleted, 0)
		self.assertTrue(_exists(orphan))


class TestCashierMayActOnAnOrphan(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.profile = frappe._dict({"name": PROFILE, "custom_allow_viewing_other_cashiers": 0})
		cls.open_profile = frappe._dict({"name": PROFILE, "custom_allow_viewing_other_cashiers": 1})

	def _as_cashier(self, profile, opening_entry):
		"""A non-manager standing at PROFILE with `opening_entry` open."""
		return [
			patch("frappe.get_roles", return_value=["All", "Sales User"]),
			patch.object(sales_order, "_get_active_pos_profile", return_value=profile),
			patch.object(sales_order, "get_current_pos_opening_entry", return_value=opening_entry),
		]

	def _check(self, so, profile, opening_entry):
		patches = self._as_cashier(profile, opening_entry)
		for p in patches:
			p.start()
		try:
			_assert_held_order_access(so)
		finally:
			for p in patches:
				p.stop()

	def test_an_orphan_on_my_own_till_can_be_opened(self):
		"""The regression: this threw, so the order was visible and unusable."""
		orphan = _held_order(opening_entry="")

		self._check(orphan, self.profile, "POS-OPE-CURRENT")

	def test_an_order_from_my_own_shift_is_unaffected(self):
		mine = _held_order(opening_entry="POS-OPE-CURRENT")

		self._check(mine, self.profile, "POS-OPE-CURRENT")

	def test_another_cashier_s_orphan_is_refused_on_a_closed_till(self):
		theirs = _held_order(opening_entry="", owner="somebody-else@example.com")

		with self.assertRaises(frappe.ValidationError):
			self._check(theirs, self.profile, "POS-OPE-CURRENT")

	def test_another_cashier_s_orphan_is_allowed_where_the_till_permits_it(self):
		"""Same rule the Draft tab lists by: shown and openable, or neither."""
		theirs = _held_order(opening_entry="", owner="somebody-else@example.com")

		self._check(theirs, self.open_profile, "POS-OPE-CURRENT")

	def test_an_orphan_on_a_different_till_is_still_refused(self):
		elsewhere = _held_order(opening_entry="", profile="SOME-OTHER-TILL")

		with self.assertRaises(frappe.ValidationError):
			self._check(elsewhere, self.profile, "POS-OPE-CURRENT")

	def test_an_order_belonging_to_another_live_shift_is_still_refused(self):
		live = _opening_entry(hours_ago=1)
		other_session = _held_order(opening_entry=live.name)

		with self.assertRaises(frappe.ValidationError):
			self._check(other_session, self.profile, "POS-OPE-CURRENT")
