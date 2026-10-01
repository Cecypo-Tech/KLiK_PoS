"""Closing a shift clears held orders only where the till asks for it, and never rewinds numbering.

Held orders were deleted on every shift close, whatever the till said: at Allparts, where the
sales staff hold orders against the one open shift on "Allparts Sales", closing it at 12:07
deleted 61 orders still waiting on customers - with "Clear Draft Invoices on Closing Shift"
off. Held orders are what the POS now holds a sale as, so that checkbox decides for them too.

The sweep also deleted newest first, and frappe winds a naming series back whenever the
newest document goes: after each close new held orders were numbered from SO-00001 again,
so the same names were deleted three times in one day.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import pos_entry
from klik_pos.api.sales_order import delete_held_orders_for_opening_entry
from klik_pos.tests.test_held_order_orphans import PROFILE, _held_order, _opening_entry


def _exists(so):
	return bool(frappe.db.exists("Sales Order", so.name))


def _series_current(name):
	"""The counter of the series `name` was drawn from, read the way frappe reverts it."""
	prefix = name.rstrip("0123456789")
	row = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", prefix)
	return row[0][0] if row else None


class TestTheTillDecides(FrappeTestCase):
	def _close(self, shift, clear):
		real = frappe.db.get_value

		def till_setting(doctype, name=None, fieldname=None, *args, **kwargs):
			if doctype == "POS Profile" and fieldname == "custom_clear_draft_invoices":
				return clear
			return real(doctype, name, fieldname, *args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=till_setting), patch.object(
			pos_entry.frappe.logger(), "warning", side_effect=AssertionError("the close itself failed")
		):
			pos_entry._clear_held_orders_on_close(shift)

	def test_a_till_that_keeps_drafts_keeps_its_held_orders(self):
		"""The regression: SO-00015 and 60 others, deleted by closing a shift."""
		shift = _opening_entry(hours_ago=2)
		held = _held_order(opening_entry=shift.name, minutes_ago=30)
		stranded = _held_order(opening_entry="", minutes_ago=240)

		self._close(shift, clear=0)

		self.assertTrue(_exists(held))
		self.assertTrue(_exists(stranded))

	def test_a_till_that_clears_drafts_clears_its_held_orders(self):
		shift = _opening_entry(hours_ago=2)
		held = _held_order(opening_entry=shift.name, minutes_ago=30)

		self._close(shift, clear=1)

		self.assertFalse(_exists(held))


class TestNumberingIsNotRewound(FrappeTestCase):
	def test_the_sweep_leaves_the_series_where_it_was(self):
		shift = _opening_entry(hours_ago=2)
		orders = [_held_order(opening_entry=shift.name, minutes_ago=30) for _ in range(3)]
		before = _series_current(orders[-1].name)

		delete_held_orders_for_opening_entry(shift.name)

		self.assertFalse(any(_exists(so) for so in orders))
		self.assertEqual(_series_current(orders[-1].name), before)

	def test_taking_a_checked_out_order_off_the_held_tab_leaves_the_series_too(self):
		from klik_pos.api.sales_order import _remove_checked_out_order

		so = _held_order(opening_entry="", minutes_ago=5)
		before = _series_current(so.name)

		_remove_checked_out_order(so.name)

		self.assertFalse(_exists(so))
		self.assertEqual(_series_current(so.name), before)
