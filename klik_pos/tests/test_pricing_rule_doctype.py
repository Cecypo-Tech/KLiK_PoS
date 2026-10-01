"""Cart pricing names the transaction it prices.

ERPNext v16 (48635ee6, 2026-09-23) made apply_pricing_rule refuse any call whose
args.doctype is not a pricing transaction ("Invalid doctype"). klik_pos sent none, so
every cart change logged a "Pricing Rule Error" and the cart got no pricing rules at
all. The stand-in below applies that same gate, so these tests fail on an ERPNext
without it too.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

try:
    # The gate's own list, once the installed ERPNext has it.
    from erpnext.accounts.doctype.pricing_rule.pricing_rule import PRICING_TRANSACTION_DOCTYPES as ALLOWED
except ImportError:
    # Its selling side, for an ERPNext from before 48635ee6.
    ALLOWED = {"Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice", "Opportunity"}

ITEMS = [{"doctype": "Sales Invoice Item", "name": "", "item_code": "_Test Item", "qty": 1, "price_list_rate": 100}]
CONTEXT = {"company": "_Test Company", "currency": "INR", "customer": "_Test Customer", "price_list": "Standard Selling"}


class TestCartPricingNamesItsTransaction(FrappeTestCase):
    def _run(self, module):
        calls = []

        def gated_apply_pricing_rule(args, doc=None):
            if args.get("doctype") not in ALLOWED:
                frappe.throw("Invalid doctype", frappe.PermissionError)
            frappe.has_permission(args.doctype, doc=None, throw=True)
            calls.append(args)
            return [{"has_pricing_rule": 0, "pricing_rules": ""}]

        # log_error writes outside the test's rollback; a red run must not leave entries behind.
        with patch(f"{module.__name__}.apply_pricing_rule", side_effect=gated_apply_pricing_rule), patch(
            f"{module.__name__}.frappe.log_error"
        ) as log_error:
            result = module._apply_pricing_rules([dict(i) for i in ITEMS], CONTEXT)

        log_error.assert_not_called()
        self.assertEqual(result, [{"has_pricing_rule": 0, "pricing_rules": ""}])
        return calls[0]

    def test_get_cart_pricing_prices_a_sales_invoice(self):
        from klik_pos.api.item import pricing

        args = self._run(pricing)
        self.assertEqual(args.doctype, "Sales Invoice")
        # Each line still names itself; ERPNext copies it over the shared args per item.
        self.assertEqual(args["items"][0]["doctype"], "Sales Invoice Item")

    def test_apply_pricing_rules_to_cart_prices_a_sales_invoice(self):
        from klik_pos.api.item import pricing_rules

        args = self._run(pricing_rules)
        self.assertEqual(args.doctype, "Sales Invoice")
        self.assertEqual(args["items"][0]["doctype"], "Sales Invoice Item")
