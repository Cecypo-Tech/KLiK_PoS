"""The till's picked warehouse travels with each request, in the X-Klik-Warehouse header.

The picker only changed what the till showed: invoices, held orders, scans and batch picks
were all built from the POS Profile's own warehouse, so a cashier switched to B saw B's
stock and sold A's.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import _get_active_pos_profile
from klik_pos.klik_pos.utils import (
	WAREHOUSE_HEADER,
	checked_warehouse,
	get_current_pos_profile,
	get_current_pos_profile_lite,
)
from klik_pos.tests.pos_fixtures import pos_profile_settings


@contextmanager
def picked(warehouse):
	"""As if the till sent `warehouse` in the header."""
	before = getattr(frappe.local, "request", None)
	frappe.local.request = SimpleNamespace(headers={WAREHOUSE_HEADER: warehouse} if warehouse else {})
	try:
		yield
	finally:
		frappe.local.request = before


def other_warehouse(profile):
	"""A leaf, enabled warehouse of the till's company that is not its own."""
	return frappe.db.get_value(
		"Warehouse",
		{"company": profile.company, "is_group": 0, "disabled": 0, "name": ["!=", profile.warehouse]},
		"name",
	)


class TestPickedWarehouse(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		from klik_pos.api.sales_invoice import get_current_pos_opening_entry

		cls.ready = bool(get_current_pos_opening_entry())
		if cls.ready:
			cls.till = get_current_pos_profile()
			cls.own = cls.till.warehouse
			cls.other = other_warehouse(cls.till)
			cls.ready = bool(cls.own and cls.other)

	def setUp(self):
		if not self.ready:
			self.skipTest("no open shift with two warehouses on this site")
		frappe.set_user("Administrator")

	def test_every_resolver_hands_out_the_picked_warehouse(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(self.other):
			self.assertEqual(get_current_pos_profile().warehouse, self.other)
			self.assertEqual(_get_active_pos_profile().warehouse, self.other)
			self.assertEqual(get_current_pos_profile_lite(["warehouse"]).warehouse, self.other)

	def test_no_header_means_the_tills_own_warehouse(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(None):
			self.assertEqual(get_current_pos_profile().warehouse, self.own)

	def test_no_request_means_the_tills_own_warehouse(self):
		before = getattr(frappe.local, "request", None)
		frappe.local.request = None
		try:
			self.assertEqual(get_current_pos_profile().warehouse, self.own)
		finally:
			frappe.local.request = before

	def test_a_till_that_does_not_allow_switching_refuses(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=0), picked(self.other):
			with self.assertRaisesRegex(frappe.ValidationError, "does not allow"):
				get_current_pos_profile()

	def test_the_tills_own_warehouse_is_always_fine(self):
		with pos_profile_settings(self.till.name, allow_warehouse_change=0):
			self.assertIsNone(checked_warehouse(self.till, self.own))

	def test_a_group_warehouse_is_refused(self):
		group = frappe.db.get_value("Warehouse", {"company": self.till.company, "is_group": 1}, "name")
		with pos_profile_settings(self.till.name, allow_warehouse_change=1):
			self.till.allow_warehouse_change = 1
			with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
				checked_warehouse(self.till, group)

	def test_another_companys_warehouse_is_refused(self):
		foreign = frappe.db.get_value(
			"Warehouse", {"company": ["not in", [self.till.company, ""]], "is_group": 0}, "name"
		)
		if not foreign:
			self.skipTest("only one company with warehouses on this site")
		self.till.allow_warehouse_change = 1
		with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
			checked_warehouse(self.till, foreign)

	def test_a_warehouse_the_user_may_not_use_is_refused(self):
		user = "picked-warehouse@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Picked", "send_welcome_email": 0}).insert(ignore_permissions=True)
		perm = frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Warehouse", "for_value": self.own}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", user, force=True, ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User Permission", perm.name, force=True, ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		self.till.allow_warehouse_change = 1
		frappe.set_user(user)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot sell from"):
			checked_warehouse(self.till, self.other)

	def test_which_tills_work_is_visible_stays_on_the_tills_own_warehouse(self):
		from klik_pos.api.sales_invoice import _tills_sharing_warehouse

		with pos_profile_settings(self.till.name, allow_warehouse_change=1), picked(self.other):
			switched = _tills_sharing_warehouse(get_current_pos_profile())
		self.assertEqual(sorted(switched), sorted(_tills_sharing_warehouse(self.till)))
