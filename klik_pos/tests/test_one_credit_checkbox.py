"""The migration that leaves one credit checkbox keeps every till's credit permission.

custom_allow_credit_sales (2025-08) has been the switch since f5a31b4; the kept
custom_allow_credit_sales_as_pos (2026-07) decided only how an allowed credit sale was
booked. The kept field takes the switch's value, so no till gains or loses credit sales -
at Allparts, "Cecypo Team" had the kept box ticked for booking and credit off; it stays off.
On a site that never ran f5a31b4 the old field was hidden and unread, and credit followed
"Allow Partial Payment": that is what the kept field takes there.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.patches.v16_0.one_credit_checkbox import KEPT, OLD, carry_over_permission
from klik_pos.tests.test_opening_conflict import _profile


class TestOneCreditCheckbox(FrappeTestCase):
    def setUp(self):
        if not frappe.db.has_column("POS Profile", OLD):
            self.skipTest("this site never had the old field")

    def _till(self, **values):
        name = _profile()
        frappe.db.set_value("POS Profile", name, values)
        return name

    def _kept(self, till):
        return frappe.db.get_value("POS Profile", till, KEPT)

    def test_each_till_keeps_its_credit_permission(self):
        booked_only = self._till(**{OLD: 0, KEPT: 1})  # Cecypo Team
        both = self._till(**{OLD: 1, KEPT: 1})  # Allparts Cashier
        allowed_only = self._till(**{OLD: 1, KEPT: 0})
        neither = self._till(**{OLD: 0, KEPT: 0})  # Allparts Sales

        carry_over_permission(source=OLD)

        self.assertEqual(self._kept(booked_only), 0)
        self.assertEqual(self._kept(both), 1)
        self.assertEqual(self._kept(allowed_only), 1)
        self.assertEqual(self._kept(neither), 0)

    def test_a_site_that_never_used_the_old_field_follows_partial_payment(self):
        partial = self._till(**{OLD: 1, KEPT: 0, "allow_partial_payment": 1})
        stray_tick = self._till(**{OLD: 1, KEPT: 1, "allow_partial_payment": 0})

        carry_over_permission(source="allow_partial_payment")

        self.assertEqual(self._kept(partial), 1)
        self.assertEqual(self._kept(stray_tick), 0)
