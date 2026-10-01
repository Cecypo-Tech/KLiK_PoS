from types import SimpleNamespace

from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import _is_pos_for_credit_sale


class TestIsPosForCreditSale(FrappeTestCase):
    """One checkbox both allows a credit sale and books it as a POS sale; a till without it
    never makes one (parse_invoice_data refuses it), so is_pos follows the permission."""

    def test_a_till_without_credit_books_none(self):
        self.assertEqual(_is_pos_for_credit_sale(SimpleNamespace()), 0)
        self.assertEqual(_is_pos_for_credit_sale(SimpleNamespace(custom_allow_credit_sales_as_pos=0)), 0)

    def test_an_allowed_credit_sale_is_a_pos_sale(self):
        self.assertEqual(_is_pos_for_credit_sale(SimpleNamespace(custom_allow_credit_sales_as_pos=1)), 1)


class TestCreditSalesGate(FrappeTestCase):
    """'Allow Credit Sales' - one checkbox, custom_allow_credit_sales_as_pos - decides whether a
    till may sell on credit; an allowed credit sale is booked as a POS sale. The second,
    older custom_allow_credit_sales is gone: two near-identical boxes in two sections, and
    the one that looked like the switch was not."""

    def _parse(self, profile, **extra):
        from unittest.mock import patch

        from klik_pos.api.sales_invoice import parse_invoice_data

        data = {
            "customer": {"id": "_Test Customer"},
            "items": [{"id": "_Test Item", "quantity": 1, "price": 100}],
            "paymentMethods": [],
            "dueDate": "2099-01-01",
            **extra,
        }
        with patch("klik_pos.api.sales_invoice.get_current_pos_profile", return_value=profile):
            return parse_invoice_data(data)

    def test_the_flag_reads_allow_credit_sales(self):
        from klik_pos.api.sales_invoice import _credit_sales_allowed

        self.assertEqual(_credit_sales_allowed(SimpleNamespace()), 0)
        self.assertEqual(_credit_sales_allowed(SimpleNamespace(custom_allow_credit_sales_as_pos=1)), 1)
        # The dropped field no longer means anything.
        self.assertEqual(_credit_sales_allowed(SimpleNamespace(custom_allow_credit_sales=1)), 0)

    def test_a_credit_sale_on_a_till_without_it_is_refused(self):
        import frappe

        profile = frappe._dict(name="Till X", custom_allow_credit_sales_as_pos=0, default_sales_type="Cash")
        with self.assertRaisesRegex(frappe.ValidationError, "Credit sales are turned off"):
            self._parse(profile, isCreditSale=True)

    def test_a_till_defaulting_to_credit_without_it_sells_for_cash(self):
        import frappe

        profile = frappe._dict(name="Till X", custom_allow_credit_sales_as_pos=0, default_sales_type="Credit")
        parsed = self._parse(profile, paymentMethods=[{"method": "Cash", "amount": 100}], amountPaid=100)
        is_credit_sale = parsed[9]
        self.assertFalse(is_credit_sale)


class TestCreditSaleNeedsNoPartialPayment(FrappeTestCase):
    """A credit sale is unpaid by design; 'Allow Credit Sales' alone must let it through,
    without also switching on 'Allow Partial Payment' for every sale on the till."""

    def _unpaid_invoice(self, allow_credit_sales, customer="_Test Customer"):
        import frappe
        from erpnext.accounts.doctype.pos_profile.test_pos_profile import make_pos_profile

        profile = make_pos_profile(do_not_insert=1)
        profile.name = f"_Test Credit Gate {frappe.generate_hash(length=5)}"
        profile.allow_partial_payment = 0
        profile.custom_allow_credit_sales_as_pos = allow_credit_sales
        profile.insert(ignore_permissions=True)
        invoice = frappe.new_doc("Sales Invoice")
        invoice.pos_profile = profile.name
        invoice.customer = customer
        invoice.grand_total = invoice.rounded_total = 100
        invoice.paid_amount = 0
        invoice.total_advance = 0
        return invoice

    def test_an_unpaid_sale_on_a_credit_till_passes(self):
        self._unpaid_invoice(allow_credit_sales=1).validate_full_payment()

    def test_an_unpaid_sale_on_a_till_without_credit_is_still_refused(self):
        from klik_pos.api.sales_invoice import PartialPaymentValidationError

        with self.assertRaises(PartialPaymentValidationError):
            self._unpaid_invoice(allow_credit_sales=0).validate_full_payment()

    def test_an_unpaid_walk_in_sale_is_refused_even_on_a_credit_till(self):
        """A credit sale needs a named customer, so an unpaid walk-in invoice is not one."""
        import frappe

        from klik_pos.api.sales_invoice import PartialPaymentValidationError

        walk_in = frappe.db.get_value("Customer", {"custom_is_walkin": 1}, "name")
        if not walk_in:
            self.skipTest("no walk-in customer on this site")
        with self.assertRaises(PartialPaymentValidationError):
            self._unpaid_invoice(allow_credit_sales=1, customer=walk_in).validate_full_payment()

    def test_a_credit_sale_that_redeems_loyalty_points_passes(self):
        invoice = self._unpaid_invoice(allow_credit_sales=1)
        invoice.loyalty_amount = 20
        invoice.validate_full_payment()


class TestCreditSalesGateAllows(TestCreditSalesGate):
    def test_an_explicit_credit_sale_on_a_credit_till_passes_the_gate(self):
        import frappe

        profile = frappe._dict(name="Till Y", custom_allow_credit_sales_as_pos=1, default_sales_type="Cash")
        parsed = self._parse(profile, isCreditSale=True)
        self.assertTrue(parsed[9], "is_credit_sale")
