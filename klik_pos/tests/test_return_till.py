"""A return belongs to the till that refunds it.

The credit note was built from the original sale, so it kept the sale's till (pos_profile)
while taking the refunding shift (custom_pos_opening_entry). Refunded at "Allparts Cashier"
for a sale rung on "Allparts Sales", the cash left the Cashier drawer and was counted in the
Cashier shift - but the note said "Allparts Sales": the dashboard's per-till figures put the
refund on a till whose drawer never paid it, and the Cashier's own closing and history
lists (held to their till) left out a note their totals included.
"""

from unittest.mock import patch

import frappe

from klik_pos.tests.test_return_cash_only import CashOnlyReturnCase


class RefundingTillCase(CashOnlyReturnCase):
	def setUp(self):
		super().setUp()
		from klik_pos.tests.test_opening_conflict import _profile, _shift

		from klik_pos.tests.test_mpesa_payment_entry_first import COMPANY

		self.sold_at, self.refunded_at = _profile(), _profile()
		# Two tills of the sale's company - one shop, two counters.
		for till in (self.sold_at, self.refunded_at):
			frappe.db.set_value("POS Profile", till, "company", COMPANY)
		self.shift = _shift(self.refunded_at, "Administrator")

	def _sale_on_other_till(self):
		invoice = self._sale(300, cash=300)
		frappe.db.set_value("Sales Invoice", invoice.name, "pos_profile", self.sold_at, update_modified=False)
		return invoice


class TestReturnTakesTheRefundingTill(RefundingTillCase):
	def test_a_full_return_is_the_refunding_till_s(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._full_return(invoice)
		self.assertEqual(credit.custom_pos_opening_entry, self.shift)
		self.assertEqual(credit.pos_profile, self.refunded_at)

	def test_a_partial_return_is_the_refunding_till_s(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._partial_return(invoice, 300)
		self.assertEqual(credit.custom_pos_opening_entry, self.shift)
		self.assertEqual(credit.pos_profile, self.refunded_at)

	def test_with_no_shift_open_the_return_keeps_the_sale_s_till(self):
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=None):
			credit = self._full_return(invoice)
		self.assertEqual(credit.pos_profile, self.sold_at)

	def test_a_salesperson_pin_on_the_refunding_till_does_not_block_the_return(self):
		"""A credit note carries the sale's salesperson; the return endpoints take none."""
		frappe.db.set_value("POS Profile", self.refunded_at, "custom_sales_person_pin_required", 1)
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._full_return(invoice)
		self.assertEqual(credit.docstatus, 1)

	def test_a_shift_in_another_company_does_not_lend_the_return_its_till(self):
		other_company = frappe.db.get_value("Company", {"name": ["!=", self.refunded_company()]}, "name")
		if not other_company:
			self.skipTest("needs a second company")
		frappe.db.set_value("POS Profile", self.refunded_at, "company", other_company)
		invoice = self._sale_on_other_till()
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._full_return(invoice)
		self.assertEqual(credit.pos_profile, self.sold_at)

	def refunded_company(self):
		return frappe.db.get_value("POS Profile", self.refunded_at, "company")


TAX_TEMPLATE = "_Test Sales Taxes and Charges Template - _TC"


class TestTheRefundingTillDoesNotRetaxTheReturn(RefundingTillCase):
	"""Taking the refunding till must not take its taxes.

	ERPNext's set_pos_fields fills an empty taxes_and_charges from the invoice's POS Profile
	and then pulls that template's rows into an empty taxes table. An untaxed sale's return
	has both empty, so once it took a till with a template it gained tax the sale never
	charged: 500 sold, 580 credited, and the refund paid out the 80 too.
	"""

	def _sale_at(self, till, template=None):
		"""A cash sale of 300 rung on `till`, taxed by `template` or not at all."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		from klik_pos.tests.test_mpesa_payment_entry_first import COMPANY, CUSTOMER

		invoice = create_sales_invoice(
			company=COMPANY, customer=CUSTOMER, is_pos=1, rate=300,
			posting_date=frappe.utils.nowdate(), do_not_save=True,
		)
		invoice.pos_profile = till
		invoice.taxes_and_charges = template
		invoice.set("taxes", [])
		if template:
			invoice.set_taxes()
		invoice.calculate_taxes_and_totals()
		invoice.set("payments", [{"mode_of_payment": "Cash", "amount": invoice.grand_total}])
		invoice.insert(ignore_permissions=True)
		invoice.submit()
		return invoice

	def _return_at_refunding_till(self, invoice, partial=False):
		with patch("klik_pos.api.sales_invoice.get_current_pos_opening_entry", return_value=self.shift):
			credit = self._partial_return(invoice, invoice.grand_total) if partial else self._full_return(invoice)
		self.assertEqual(credit.pos_profile, self.refunded_at)
		return credit

	def _assert_untaxed_like(self, credit, invoice):
		self.assertFalse(invoice.taxes, "fixture: the sale must be untaxed")
		self.assertFalse(credit.taxes_and_charges, "the refunding till's template was stamped on")
		self.assertEqual([t.account_head for t in credit.taxes], [], "tax the sale never charged")
		self.assertEqual(frappe.utils.flt(credit.grand_total), -frappe.utils.flt(invoice.grand_total))

	def test_a_full_return_of_an_untaxed_sale_stays_untaxed(self):
		frappe.db.set_value("POS Profile", self.refunded_at, "taxes_and_charges", TAX_TEMPLATE)
		invoice = self._sale_at(self.sold_at)
		self._assert_untaxed_like(self._return_at_refunding_till(invoice), invoice)

	def test_a_partial_return_of_an_untaxed_sale_stays_untaxed(self):
		frappe.db.set_value("POS Profile", self.refunded_at, "taxes_and_charges", TAX_TEMPLATE)
		invoice = self._sale_at(self.sold_at)
		self._assert_untaxed_like(self._return_at_refunding_till(invoice, partial=True), invoice)

	def test_a_taxed_sale_returned_at_an_untaxed_till_keeps_its_own_tax(self):
		invoice = self._sale_at(self.sold_at, template=TAX_TEMPLATE)
		self.assertTrue(invoice.taxes, "fixture: the sale must be taxed")

		credit = self._return_at_refunding_till(invoice)

		self.assertEqual(credit.taxes_and_charges, TAX_TEMPLATE)
		self.assertEqual(
			[(t.account_head, frappe.utils.flt(t.tax_amount)) for t in credit.taxes],
			[(t.account_head, -frappe.utils.flt(t.tax_amount)) for t in invoice.taxes],
		)
		self.assertEqual(frappe.utils.flt(credit.grand_total), -frappe.utils.flt(invoice.grand_total))
