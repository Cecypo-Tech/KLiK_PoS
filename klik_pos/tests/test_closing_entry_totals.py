"""A shift's totals must count each invoice once, not once per line.

`_calculate_closing_entry_totals` LEFT JOINed `Sales Invoice Item` and then summed the
parent's `net_total` and `grand_total`, so every sum was multiplied by that invoice's
line count. A three-line invoice was counted three times. On dev, opening entry
POS-OPE-2026-00013 reported 1,466.24 over six invoices that really totalled 1,346.76 --
and the inflated figure is what the closing entry stores, what the cashier reconciles
cash against, and what the new dashboard is validated against.

Quantity now comes from the parent's own `total_qty` rather than from the item rows,
which is the number those rows would have summed to.

The invoices are linked to the opening entry by writing the column directly: the function
is a single SQL statement keyed on `custom_pos_opening_entry`, so a real POS Opening Entry
(which needs a profile, a user and balance details) would add setup without adding
coverage. The token is unique per run so a parallel or repeated run cannot collide.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.pos_entry import _calculate_closing_entry_totals

COMPANY = "Dev Co"
ITEM = "Consulting"


def _make_customer(name):
	if frappe.db.exists("Customer", name):
		return name
	doc = frappe.get_doc(
		{"doctype": "Customer", "customer_name": name, "customer_type": "Individual"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_invoice(customer, lines, opening_entry):
	"""A submitted invoice with `lines` item rows, attached to `opening_entry`."""
	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.company = COMPANY
	si.is_pos = 0
	for qty, rate in lines:
		si.append("items", {"item_code": ITEM, "qty": qty, "rate": rate})
	si.insert(ignore_permissions=True)
	si.submit()
	frappe.db.set_value(
		"Sales Invoice", si.name, "custom_pos_opening_entry", opening_entry, update_modified=False
	)
	return si


class TestClosingEntryTotals(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		suffix = frappe.generate_hash(length=8)
		cls.opening_entry = f"TEST-OPE-{suffix}"
		cls.customer = _make_customer(f"CET Test Customer {suffix}")

		# Three lines and two lines: line counts differ, so a fanout cannot be mistaken
		# for a constant multiplier that a single-invoice test would miss.
		cls.three_line = _make_invoice(cls.customer, [(1, 100), (2, 50), (3, 10)], cls.opening_entry)
		cls.two_line = _make_invoice(cls.customer, [(1, 200), (4, 25)], cls.opening_entry)

		# Same shape, no opening entry: proves the filter still selects.
		cls.unlinked = _make_invoice(cls.customer, [(1, 999)], "")

		cls.totals = _calculate_closing_entry_totals(cls.opening_entry)

	def test_grand_total_counts_each_invoice_once(self):
		"""The regression. Before the fix this was 3x the first invoice plus 2x the second."""
		expected = flt(self.three_line.grand_total) + flt(self.two_line.grand_total)

		self.assertAlmostEqual(self.totals["grand_total"], expected, places=2)

	def test_net_total_counts_each_invoice_once(self):
		expected = flt(self.three_line.net_total) + flt(self.two_line.net_total)

		self.assertAlmostEqual(self.totals["net_total"], expected, places=2)

	def test_quantity_is_the_sum_of_the_lines(self):
		"""total_qty must still be the item quantity, not an invoice count."""
		self.assertAlmostEqual(self.totals["total_quantity"], 1 + 2 + 3 + 1 + 4, places=2)

	def test_the_inflated_figure_is_actually_different(self):
		"""Pins that the fixtures can tell the two queries apart.

		Multi-line invoices are what make the fanout visible; if a future edit reduced these
		fixtures to one line each, every assertion above would still pass while proving
		nothing. This computes what the old joined query would have returned and requires it
		to disagree.
		"""
		inflated = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(si.grand_total), 0)
			FROM `tabSales Invoice` si
			LEFT JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
			WHERE si.custom_pos_opening_entry = %s AND si.docstatus = 1
			""",
			(self.opening_entry,),
		)[0][0]

		self.assertGreater(flt(inflated), self.totals["grand_total"])

	def test_invoices_of_another_shift_are_not_counted(self):
		self.assertNotIn(flt(self.unlinked.grand_total), [self.totals["grand_total"]])
		self.assertAlmostEqual(
			self.totals["grand_total"],
			flt(self.three_line.grand_total) + flt(self.two_line.grand_total),
			places=2,
		)

	def test_a_shift_with_no_invoices_is_zero_not_an_error(self):
		totals = _calculate_closing_entry_totals(f"TEST-OPE-EMPTY-{frappe.generate_hash(length=6)}")

		self.assertEqual(totals, {"total_quantity": 0.0, "net_total": 0.0, "grand_total": 0.0})


class TestClosingExpectsPaymentEntries(FrappeTestCase):
	def test_a_shift_stamped_payment_entry_counts_toward_expected(self):
		"""M-Pesa money is on Payment Entries now, and the closing entry compared the
		drawer against payment rows alone - which would have said the till took none."""
		from klik_pos.api.pos_entry import _calculate_payment_reconciliation

		opening = frappe.new_doc("POS Opening Entry")
		opening.update({"pos_profile": "_Test POS Profile", "company": "Dev Co", "user": frappe.session.user,
			"period_start_date": frappe.utils.add_to_date(None, hours=-1), "posting_date": frappe.utils.nowdate()})
		opening.append("balance_details", {"mode_of_payment": "Cash", "opening_amount": 0})
		opening.flags.ignore_validate = True
		opening.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_value("POS Opening Entry", opening.name, {"docstatus": 1, "status": "Open"}, update_modified=False)
		opening.reload()

		receivable, bank = frappe.db.get_value("Company", "Dev Co", ["default_receivable_account", "default_cash_account"])
		pe = frappe.get_doc({"doctype": "Payment Entry", "payment_type": "Receive", "party_type": "Customer", "party": "Walk In",
			"company": "Dev Co", "posting_date": frappe.utils.nowdate(), "mode_of_payment": "Cash", "paid_from": receivable,
			"paid_to": bank, "paid_amount": 300, "received_amount": 300, "source_exchange_rate": 1, "target_exchange_rate": 1,
			"paid_from_account_currency": "KES", "paid_to_account_currency": "KES", "custom_pos_opening_entry": opening.name})
		pe.insert(ignore_permissions=True)
		pe.submit()

		rows = _calculate_payment_reconciliation(opening, {"closing_balance": {"Cash": 300}})

		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")
		self.assertEqual(flt(cash["expected_amount"]), 300.0)
		self.assertEqual(flt(cash["difference"]), 0.0)
