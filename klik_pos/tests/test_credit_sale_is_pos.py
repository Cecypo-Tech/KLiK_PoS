from types import SimpleNamespace

from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_invoice import _is_pos_for_credit_sale


class TestIsPosForCreditSale(FrappeTestCase):
    def test_defaults_to_zero_when_flag_unset(self):
        # Regression guard for the Jul 6 fix (commit 633227a): credit sales must
        # stay is_pos=0 unless the POS Profile explicitly opts in.
        pos_profile = SimpleNamespace()
        self.assertEqual(_is_pos_for_credit_sale(pos_profile), 0)

    def test_zero_when_flag_explicitly_off(self):
        pos_profile = SimpleNamespace(custom_allow_credit_sales_as_pos=0)
        self.assertEqual(_is_pos_for_credit_sale(pos_profile), 0)

    def test_one_when_flag_enabled(self):
        pos_profile = SimpleNamespace(custom_allow_credit_sales_as_pos=1)
        self.assertEqual(_is_pos_for_credit_sale(pos_profile), 1)


class TestCreditSalesGate(FrappeTestCase):
    """'Allow Credit Sales' (custom_allow_credit_sales) decides whether a till may sell on credit."""

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
        self.assertEqual(_credit_sales_allowed(SimpleNamespace(custom_allow_credit_sales=1)), 1)
        # "as POS" only decides is_pos on a credit sale; it does not allow one.
        self.assertEqual(_credit_sales_allowed(SimpleNamespace(custom_allow_credit_sales_as_pos=1)), 0)

    def test_a_credit_sale_on_a_till_without_it_is_refused(self):
        import frappe

        profile = frappe._dict(name="Till X", custom_allow_credit_sales=0, default_sales_type="Cash")
        with self.assertRaisesRegex(frappe.ValidationError, "Credit sales are turned off"):
            self._parse(profile, isCreditSale=True)

    def test_a_till_defaulting_to_credit_without_it_sells_for_cash(self):
        import frappe

        profile = frappe._dict(name="Till X", custom_allow_credit_sales=0, default_sales_type="Credit")
        parsed = self._parse(profile, paymentMethods=[{"method": "Cash", "amount": 100}], amountPaid=100)
        is_credit_sale = parsed[9]
        self.assertFalse(is_credit_sale)


class TestCreditSaleNeedsNoPartialPayment(FrappeTestCase):
    """A credit sale is unpaid by design; 'Allow Credit Sales' alone must let it through,
    without also switching on 'Allow Partial Payment' for every sale on the till."""

    def _unpaid_invoice(self, allow_credit_sales):
        import frappe
        from erpnext.accounts.doctype.pos_profile.test_pos_profile import make_pos_profile

        profile = make_pos_profile(do_not_insert=1)
        profile.name = f"_Test Credit Gate {frappe.generate_hash(length=5)}"
        profile.allow_partial_payment = 0
        profile.custom_allow_credit_sales = allow_credit_sales
        profile.insert(ignore_permissions=True)
        invoice = frappe.new_doc("Sales Invoice")
        invoice.pos_profile = profile.name
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
