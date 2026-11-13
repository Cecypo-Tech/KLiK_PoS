import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.customer import get_customer_overdue_invoices


class TestGetCustomerOverdueInvoices(FrappeTestCase):
    def test_empty_customer_returns_no_overdue(self):
        result = get_customer_overdue_invoices(customer="")
        self.assertFalse(result["has_overdue"])
        self.assertEqual(result["invoices"], [])
        self.assertEqual(result["customer_name"], "")

    def test_nonexistent_customer_returns_empty(self):
        result = get_customer_overdue_invoices(customer="Nonexistent Customer XYZ 9999")
        self.assertFalse(result["has_overdue"])
        self.assertEqual(result["invoices"], [])

    def test_return_shape(self):
        result = get_customer_overdue_invoices(customer="Nonexistent Customer XYZ 9999")
        self.assertIn("has_overdue", result)
        self.assertIn("invoices", result)
        self.assertIn("customer_name", result)
        self.assertIsInstance(result["invoices"], list)

    def test_company_filter_accepted(self):
        # Should not raise even with a company that doesn't exist
        result = get_customer_overdue_invoices(
            customer="Nonexistent Customer XYZ 9999",
            company="Nonexistent Company"
        )
        self.assertFalse(result["has_overdue"])


from unittest.mock import patch

from frappe.utils import add_days, today

_MOD = "klik_pos.api.customer"


class TestOverdueBalanceGate(FrappeTestCase):
    """Only a till that shows overdue warnings (or a manager) may read a customer's balance."""

    def _call(self, manager, flag, rows=()):
        with patch("klik_pos.api.shift.is_shift_manager", return_value=manager), \
             patch(f"{_MOD}._till_shows_overdue", return_value=flag), \
             patch(f"{_MOD}.frappe.db.sql", return_value=list(rows)):
            return get_customer_overdue_invoices(customer="Any Customer")

    def test_refused_when_till_hides_overdue(self):
        with self.assertRaises(frappe.PermissionError):
            self._call(manager=False, flag=False)

    def test_manager_may_read(self):
        self.assertIn("total_outstanding", self._call(manager=True, flag=False))

    def test_total_covers_due_and_overdue_list_only_overdue(self):
        rows = [
            frappe._dict(name="SINV-OLD", due_date=add_days(today(), -5), grand_total=3000, outstanding_amount=2000, currency="KES", customer_name="C"),
            frappe._dict(name="SINV-NEW", due_date=add_days(today(), 1), grand_total=3000, outstanding_amount=3000, currency="KES", customer_name="C"),
        ]
        result = self._call(manager=False, flag=True, rows=rows)
        self.assertEqual(result["total_outstanding"], 5000)
        self.assertEqual([i.name for i in result["invoices"]], ["SINV-OLD"])
        self.assertTrue(result["has_overdue"])
