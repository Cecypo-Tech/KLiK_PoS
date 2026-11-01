"""The Z-report's figures, checked against what klik files when the shift closes.

Sales go through klik's own invoice builder on a till of the test's own (open_own_shift),
moved to a warehouse of its own so the day-scope figures see only this test's documents.
"""

import re
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from klik_pos.z_report import build_z_report, render_escpos, render_html

TILL = "_Test Z Till"
BRANCH = "_Test Z Branch"
OTHER_BRANCH = "_Test Z Branch 2"
ITEM = "_TEST-Z-ITEM"
CUSTOMER = "_Test Z Customer"
EXPENSE_TYPE = "Z Newspaper"


def _installed():
	return "klik_pos" in frappe.get_installed_apps()


def _drop_user(email):
	frappe.set_user("Administrator")
	for p in frappe.get_all("User Permission", {"user": email}, pluck="name"):
		frappe.delete_doc("User Permission", p, force=True, ignore_permissions=True)
	frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()


def _cancel_delete(doctype, names):
	for name in names:
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)


def _purge():
	"""Every document the tests make: receipts first, then expenses, then sales (returns first)."""
	frappe.set_user("Administrator")
	_cancel_delete("Payment Entry", frappe.get_all("Payment Entry", {"party": CUSTOMER}, pluck="name"))
	if frappe.db.has_column("Journal Entry", "custom_pos_profile"):
		_cancel_delete(
			"Journal Entry", frappe.get_all("Journal Entry", {"custom_pos_profile": TILL}, pluck="name")
		)
	_cancel_delete(
		"Sales Invoice",
		frappe.get_all(
			"Sales Invoice", {"customer": CUSTOMER}, pluck="name", order_by="is_return desc, creation desc"
		),
	)
	frappe.db.commit()


@unittest.skipUnless(_installed(), "klik_pos is not installed")
class TestZReport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from klik_pos.api.mpesa import is_mpesa_mode
		from klik_pos.api.sales_invoice import get_current_pos_opening_entry
		from klik_pos.tests.pos_fixtures import open_own_shift, pick_payment_mode

		frappe.set_user("Administrator")
		profile = open_own_shift(cls, TILL)
		if not profile:
			raise unittest.SkipTest("no till to copy")
		cls.addClassCleanup(cls._drop_masters)
		cls.addClassCleanup(_purge)  # LIFO: runs before open_own_shift drops the till
		cls.company = profile.company
		cls.shift = get_current_pos_opening_entry()

		account_of = {
			r.parent: r.default_account
			for r in frappe.get_all(
				"Mode of Payment Account", {"company": cls.company}, ["parent", "default_account"]
			)
			if r.default_account
		}
		cls.cash = pick_payment_mode(TILL)
		cls.other = next(
			# A typed amount on an M-Pesa mode is refused without a receipt behind it.
			(
				p.mode_of_payment
				for p in profile.payments
				if p.mode_of_payment != cls.cash
				and account_of.get(p.mode_of_payment)
				and not is_mpesa_mode(p.mode_of_payment)
			),
			None,
		)
		if not (account_of.get(cls.cash) and cls.other):
			raise unittest.SkipTest("the till needs two modes with accounts")
		cls.other_account = account_of[cls.other]

		cls.warehouse = cls._ensure_warehouse(BRANCH)
		cls.other_warehouse = cls._ensure_warehouse(OTHER_BRANCH)
		cls._ensure_masters()
		profile = frappe.get_doc("POS Profile", TILL)
		profile.warehouse = cls.warehouse
		profile.allow_partial_payment = 1
		if profile.meta.has_field("custom_expense_account"):
			profile.custom_expense_account = account_of[cls.cash]
			profile.custom_expenses_need_approval = 0
			profile.set(
				"custom_expense_types",
				[
					{
						"label": EXPENSE_TYPE,
						"expense_account": frappe.db.get_value(
							"Account",
							{"company": cls.company, "root_type": "Expense", "is_group": 0},
							"name",
							order_by="name",
						),
					}
				],
			)
			profile.applicable_for_users[0].custom_can_record_expenses = 1
		profile.save(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def _ensure_warehouse(cls, branch):
		name = frappe.db.get_value("Warehouse", {"warehouse_name": branch, "company": cls.company})
		if name:
			return name
		return (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": branch,
					"company": cls.company,
					"parent_warehouse": frappe.db.get_value(
						"Warehouse", {"company": cls.company, "is_group": 1}, "name", order_by="lft"
					),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	@classmethod
	def _ensure_masters(cls):
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_type": "Individual",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				}
			).insert(ignore_permissions=True)

	@classmethod
	def _drop_masters(cls):
		for doctype, name in (("Item", ITEM), ("Customer", CUSTOMER)):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(_purge)

	# ---- helpers ---------------------------------------------------------------------

	def _items(self):
		return [{"id": ITEM, "item_code": ITEM, "quantity": 1, "price": 100, "uom": "Nos"}]

	def _total(self):
		from klik_pos.tests.pos_fixtures import payable_total

		return flt(payable_total(CUSTOMER, self._items(), self.cash))

	def _sell(self, payments=None):
		"""A till sale on the test shift. `payments` is {mode: amount}; default: paid in full in cash."""
		from klik_pos.api.sales_invoice import build_sales_invoice_doc

		doc = build_sales_invoice_doc(CUSTOMER, self._items(), 0, None, self.cash, "B2C")
		doc.is_pos = 1
		doc.set("payments", [])
		for mode, amount in (payments or {self.cash: self._total()}).items():
			doc.append("payments", {"mode_of_payment": mode, "amount": amount})
		doc.insert(ignore_permissions=True)
		doc.submit()
		frappe.db.commit()
		return doc

	def _return(self, invoice):
		from klik_pos.api.sales_invoice import return_sales_invoice

		result = return_sales_invoice(invoice.name)
		self.assertTrue(result.get("success"), result.get("message"))
		frappe.db.commit()
		return result["return_invoice"]

	def _desk_invoice(self, posting_date=None, warehouse=None, advances=False):
		"""A desk sale on credit, at the test branch unless `warehouse` says otherwise ("" = none).
		`advances`: settle it from the customer's unallocated advances."""
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": self.company,
				"customer": CUSTOMER,
				"posting_date": posting_date or nowdate(),
				"set_posting_time": 1,
				"due_date": posting_date or nowdate(),
				"set_warehouse": self.warehouse if warehouse is None else warehouse,
				"allocate_advances_automatically": 1 if advances else 0,
			}
		)
		doc.append("items", {"item_code": ITEM, "qty": 1, "rate": 100})
		doc.set_missing_values()
		doc.insert(ignore_permissions=True)
		doc.submit()
		frappe.db.commit()
		return doc

	def _receipt(self, amount, invoice=None, stamp=True, allocations=None, posting_date=None):
		"""A Receive Payment Entry in the other mode, optionally allocated and stamped with the shift."""
		pe = frappe.new_doc("Payment Entry")
		pe.update(
			{
				"payment_type": "Receive",
				"party_type": "Customer",
				"party": CUSTOMER,
				"company": self.company,
				"posting_date": posting_date or nowdate(),
				"mode_of_payment": self.other,
				"paid_to": self.other_account,
				"paid_amount": amount,
				"received_amount": amount,
				"reference_no": "Z-TEST",
				"reference_date": nowdate(),
			}
		)
		if stamp:
			pe.custom_pos_opening_entry = self.shift
		for name, allocated in allocations or ([(invoice, amount)] if invoice else []):
			pe.append(
				"references",
				{"reference_doctype": "Sales Invoice", "reference_name": name, "allocated_amount": allocated},
			)
		pe.setup_party_account_field()
		pe.set_missing_values()
		pe.insert(ignore_permissions=True)
		pe.submit()
		frappe.db.commit()
		return pe

	def _shift(self):
		return build_z_report(opening_entry=self.shift)

	def _day(self, date=None):
		return build_z_report(warehouse=self.warehouse, date=date or nowdate())

	# ---- tests -------------------------------------------------------------------------

	def test_shift_matches_klik_expected(self):
		from klik_pos.api.pos_entry import expected_by_mode

		total = self._total()
		self._sell({self.cash: total + 50})  # 50 change
		returned = self._sell()
		self._sell({self.other: total})
		self._return(returned)
		spent = 0
		if frappe.get_meta("POS Profile").has_field("custom_expense_account"):
			from klik_pos.api.expense import record_expense

			spent = 30
			record_expense(EXPENSE_TYPE, spent)

		klik = expected_by_mode(self.shift)
		ours = {row["mode"]: row for row in self._shift()["cash_position"]}
		self.assertEqual(set(ours), set(klik))
		for mode, row in klik.items():
			self.assertAlmostEqual(ours[mode]["expected"], flt(row["expected_amount"]), places=2, msg=mode)
		self.assertAlmostEqual(ours[self.cash]["expected"], total - spent, 2)  # the fixture's float is 0

	def test_returns_listed_not_double_subtracted(self):
		total = self._total()
		self._sell()
		self._return(self._sell())

		report = self._shift()
		self.assertAlmostEqual(report["tender_total"], total, 2)
		self.assertEqual(report["returns"]["count"], 1)
		self.assertAlmostEqual(report["returns"]["total"], -total, 2)
		self.assertAlmostEqual(
			report["total_balance"],
			report["tender_total"] + report["credit_total"] - report["expense_total"],
			2,
		)
		self.assertAlmostEqual(sum(u["total"] for u in report["users"]), report["tender_total"], 2)
		self.assertEqual(report["sales_count"], 2)

	def test_same_shift_mpesa_receipt_not_in_credit_collected(self):
		total = self._total()
		half = flt(total / 2, 2)
		invoice = self._sell({self.cash: half})
		self._receipt(flt(total - half, 2), invoice=invoice.name)

		report = self._shift()
		tenders = {t["mode"]: t["amount"] for t in report["tenders"]}
		self.assertAlmostEqual(tenders[self.other], total - half, 2)
		self.assertAlmostEqual(report["tender_total"], total, 2)
		self.assertEqual(report["credit_total"], 0)
		self.assertEqual(report["outstanding"], [])

	def test_old_debt_paid_today_is_credit_collected(self):
		old = self._desk_invoice(posting_date=add_days(nowdate(), -1))
		amount = flt(old.outstanding_amount)
		self._receipt(amount, invoice=old.name)

		report = self._shift()
		self.assertAlmostEqual(report["credit_total"], amount, 2)
		self.assertEqual(report["credit_collected"], [{"mode": self.other, "amount": amount}])
		self.assertEqual(report["tender_total"], 0)
		drawer = {row["mode"]: row for row in report["cash_position"]}
		self.assertAlmostEqual(drawer[self.other]["expected"], amount, 2)

	def test_day_scope_excludes_unbranched_payment(self):
		# Excluded entries are company-wide (they have no branch), so measure the change.
		before = self._day()
		self._receipt(123, stamp=False)

		after = self._day()
		self.assertEqual(after["excluded_payment_entries"], before["excluded_payment_entries"] + 1)
		self.assertEqual(after["credit_total"], before["credit_total"])

	def test_day_scope_includes_desk_invoice_by_set_warehouse(self):
		invoice = self._desk_invoice()

		report = self._day()
		self.assertEqual(report["scope"], "day")
		self.assertEqual(report["sales_count"], 1)
		self.assertEqual((report["first_doc"], report["last_doc"]), (invoice.name, invoice.name))

	def test_empty_branch(self):
		report = self._day(date="2026-01-01")
		self.assertEqual(report["report_no"], f"{self.warehouse} 2026-01-01")
		self.assertEqual(report["sales_count"], 0)
		for key in (
			"users",
			"tenders",
			"credit_collected",
			"taxes",
			"expenses",
			"cash_position",
			"outstanding",
		):
			self.assertEqual(report[key], [], key)
		for key in (
			"tender_total",
			"credit_total",
			"discount_total",
			"net_total",
			"tax_total",
			"grand_total",
			"expense_total",
			"total_balance",
		):
			self.assertEqual(report[key], 0, key)
		self.assertEqual(report["returns"], {"count": 0, "modes": [], "total": 0})
		self.assertIsNone(report["first_doc"])

	def test_outstanding_lists_only_unpaid(self):
		credit = self._desk_invoice()
		self._sell()

		outstanding = self._day()["outstanding"]
		self.assertEqual([row["name"] for row in outstanding], [credit.name])
		self.assertAlmostEqual(outstanding[0]["outstanding_amount"], flt(credit.outstanding_amount), 2)

	def test_bad_args(self):
		with self.assertRaises(frappe.ValidationError):
			build_z_report()
		with self.assertRaises(frappe.ValidationError):
			build_z_report(warehouse="X")
		with self.assertRaises(frappe.ValidationError):
			build_z_report(opening_entry=self.shift, warehouse="X", date=nowdate())

	def test_desk_refund_to_customer_is_a_return(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit_note = make_sales_return(self._desk_invoice().name)
		credit_note.update_outstanding_for_self = 1
		credit_note.set_warehouse = None  # its branch comes from the invoice it returns
		credit_note.insert(ignore_permissions=True)
		credit_note.submit()
		frappe.db.commit()
		amount = abs(flt(credit_note.outstanding_amount))
		before = self._day()

		pe = get_payment_entry("Sales Invoice", credit_note.name, bank_account=self.other_account)
		self.assertEqual((pe.payment_type, pe.party_type), ("Pay", "Customer"), "fixture: a refund")
		pe.update({"mode_of_payment": self.other, "reference_no": "Z-REFUND", "reference_date": nowdate()})
		pe.insert(ignore_permissions=True)
		pe.submit()
		frappe.db.commit()

		after = self._day()
		self.assertIn({"mode": self.other, "amount": -amount}, after["returns"]["modes"])
		self.assertAlmostEqual(after["returns"]["total"], before["returns"]["total"], 2)  # was on account
		self.assertAlmostEqual(after["refund_total"], amount, 2)
		self.assertAlmostEqual(after["total_balance"], before["total_balance"] - amount, 2)
		self.assertEqual(after["cash_position"], before["cash_position"])

	def test_desk_receipt_split_across_branches_credits_each_its_share(self):
		here = self._desk_invoice()
		there = self._desk_invoice(warehouse=self.other_warehouse)
		a, b = flt(here.outstanding_amount), flt(there.outstanding_amount)
		# Allocated to both, plus 50 unallocated: the remainder goes to the first invoice's branch.
		self._receipt(a + b + 50, stamp=False, allocations=[(here.name, a), (there.name, b)])

		ours = self._day()
		theirs = build_z_report(warehouse=self.other_warehouse, date=nowdate())
		self.assertAlmostEqual(ours["credit_total"], 50, 2)
		self.assertAlmostEqual(ours["tender_total"], a, 2)
		self.assertEqual(theirs["credit_total"], 0)
		self.assertAlmostEqual(theirs["tender_total"], b, 2)

	def test_unbranched_invoice_and_shift_receipt_are_counted(self):
		# Both counts are company-wide (no branch), so measure the change.
		before = self._day()
		self._desk_invoice(warehouse="")
		self.assertEqual(self._day()["excluded_invoices"], before["excluded_invoices"] + 1)

		frappe.db.set_value("POS Profile", TILL, "warehouse", None)
		self.addCleanup(frappe.db.commit)
		self.addCleanup(frappe.db.set_value, "POS Profile", TILL, "warehouse", self.warehouse)
		frappe.db.commit()
		before = self._day()
		self._receipt(77)  # stamped with a shift whose till has no warehouse
		self.assertEqual(self._day()["excluded_payment_entries"], before["excluded_payment_entries"] + 1)
		self.assertEqual(self._shift()["excluded_invoices"], 0)

	def test_desk_return_without_warehouse_takes_its_original_branch(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		sold = self._desk_invoice()
		before = self._day()
		credit_note = make_sales_return(sold.name)
		credit_note.set_warehouse = None  # as desk "Make Return" leaves it
		credit_note.insert(ignore_permissions=True)
		credit_note.submit()
		frappe.db.commit()

		after = self._day()
		self.assertEqual(after["returns"]["count"], 1)
		self.assertAlmostEqual(after["returns"]["total"], -flt(sold.grand_total), 2)
		self.assertEqual(after["excluded_invoices"], before["excluded_invoices"])

	def test_desk_credit_sale_is_on_credit_not_in_totals(self):
		invoice = self._desk_invoice()
		total = flt(invoice.base_rounded_total or invoice.base_grand_total)

		report = self._day()
		self.assertAlmostEqual(report["on_credit_total"], total, 2)
		user = {u["user"]: u for u in report["users"]}[invoice.owner]
		self.assertAlmostEqual(user["on_credit"], total, 2)
		self.assertEqual(user["total"], 0)
		self.assertEqual((report["tender_total"], report["total_balance"]), (0, 0))
		self.assertIn("On credit (not in totals)", render_escpos(report, width=42))

	def test_sale_settled_by_advance_is_not_on_credit(self):
		# Advance posted yesterday (outside scope) covers the whole sale.
		self._receipt(1000, stamp=False, posting_date=add_days(nowdate(), -1))
		self.assertEqual(self._day()["on_credit_total"], 0)  # fixture: nothing sold yet
		paid = self._desk_invoice(advances=True)
		self.assertEqual(flt(paid.outstanding_amount), 0, "fixture: settled by the advance")
		self.assertEqual(self._day()["on_credit_total"], 0)

	def test_partial_advance_today_counted_once(self):
		# Today's advance appears both as an advance row and as a reference row on the entry.
		self._receipt(50, stamp=False)
		invoice = self._desk_invoice(advances=True)
		total = flt(invoice.base_rounded_total or invoice.base_grand_total)
		self.assertAlmostEqual(flt(invoice.outstanding_amount), total - 50, 2, "fixture")
		self.assertAlmostEqual(self._day()["on_credit_total"], total - 50, 2)

	def test_foreign_currency_sale_in_company_currency(self):
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		currency = "USD" if company_currency != "USD" else "EUR"
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": self.company,
				"customer": CUSTOMER,
				"currency": currency,
				"conversion_rate": 100,
				"posting_date": nowdate(),
				"due_date": nowdate(),
				"set_warehouse": self.warehouse,
			}
		)
		doc.append("items", {"item_code": ITEM, "qty": 1, "rate": 2})
		doc.set_missing_values()
		doc.conversion_rate = 100
		try:
			doc.insert(ignore_permissions=True)
		except frappe.ValidationError as e:
			raise unittest.SkipTest(f"foreign-currency invoice not possible here: {e}") from e
		doc.submit()
		frappe.db.commit()
		self.assertEqual(flt(doc.conversion_rate), 100, "fixture")

		report = self._day()
		self.assertAlmostEqual(report["grand_total"], flt(doc.base_grand_total), 2)
		self.assertAlmostEqual(report["net_total"], flt(doc.base_net_total), 2)
		self.assertAlmostEqual(
			report["on_credit_total"], flt(doc.base_rounded_total or doc.base_grand_total), 2
		)
		self.assertAlmostEqual(report["outstanding"][0]["outstanding_amount"], flt(doc.base_grand_total), 0)

	def test_write_off_is_its_own_line(self):
		if not frappe.get_cached_value("Company", self.company, "write_off_account"):
			raise unittest.SkipTest("company has no write-off account")
		from klik_pos.api.sales_invoice import build_sales_invoice_doc

		total = self._total()
		doc = build_sales_invoice_doc(CUSTOMER, self._items(), 0, None, self.cash, "B2C")
		doc.is_pos = 1
		doc.set("payments", [{"mode_of_payment": self.cash, "amount": total - 10}])
		doc.write_off_amount = 10
		doc.insert(ignore_permissions=True)
		doc.submit()
		frappe.db.commit()
		self.assertAlmostEqual(flt(doc.write_off_amount), 10, 2, "fixture")

		report = self._shift()
		self.assertAlmostEqual(report["written_off_total"], 10, 2)
		self.assertEqual(report["on_credit_total"], 0)
		self.assertAlmostEqual(report["tender_total"], total - 10, 2)

	def test_refund_split_across_branches_books_each_its_share(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		notes = []
		for warehouse in (self.warehouse, self.other_warehouse):
			note = make_sales_return(self._desk_invoice(warehouse=warehouse).name)
			note.update_outstanding_for_self = 1
			note.insert(ignore_permissions=True)
			note.submit()
			notes.append(note)
		frappe.db.commit()
		a, b = (abs(flt(n.outstanding_amount)) for n in notes)
		pe = frappe.new_doc("Payment Entry")
		pe.update(
			{
				"payment_type": "Pay",
				"party_type": "Customer",
				"party": CUSTOMER,
				"company": self.company,
				"posting_date": nowdate(),
				"mode_of_payment": self.other,
				"paid_from": self.other_account,
				"paid_amount": a + b + 20,
				"received_amount": a + b + 20,
				"reference_no": "Z-SPLIT",
				"reference_date": nowdate(),
			}
		)
		for note, amount in zip(notes, (a, b), strict=True):
			pe.append(
				"references",
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": note.name,
					"allocated_amount": -amount,
				},
			)
		pe.setup_party_account_field()
		pe.set_missing_values()
		pe.insert(ignore_permissions=True)
		pe.submit()
		frappe.db.commit()

		ours = self._day()
		theirs = build_z_report(warehouse=self.other_warehouse, date=nowdate())
		self.assertAlmostEqual(ours["refund_total"], a + 20, 2)  # the remainder: first allocated branch
		self.assertAlmostEqual(theirs["refund_total"], b, 2)

	def test_shift_header(self):
		r = build_z_report(opening_entry=self.shift)
		self.assertEqual(r["pos_profile"], TILL)
		self.assertEqual(r["cashier"], frappe.db.get_value("POS Opening Entry", self.shift, "user"))
		self.assertEqual(r["tax_id"], frappe.db.get_value("Company", self.company, "tax_id"))
		self.assertEqual(r["printed_by"], "Administrator")
		day = build_z_report(warehouse=self.warehouse, date=nowdate())
		self.assertIsNone(day["pos_profile"])
		self.assertEqual(day["printed_by"], "Administrator")

	def test_escpos_refused_without_closing_or_print_permission(self):
		from klik_pos.z_report import z_report_escpos

		with self.assertRaises(frappe.PermissionError):
			z_report_escpos(self.shift)  # still open: no submitted closing
		self.addCleanup(
			setattr, frappe.flags, "ignore_print_permissions", frappe.flags.ignore_print_permissions
		)
		frappe.flags.ignore_print_permissions = True
		with self.assertRaises(frappe.PermissionError):
			z_report_escpos(self.shift)  # the flag never lifts the submitted-closing rule


HEADERS = [
	"Z REPORT",
	"Sales by user",
	"Tender types",
	"Credit collected / deposits",
	"Returns",
	"Discounts",
	"Tax",
	"Expenses",
	"Cash position",
	"Total balance",
]


def _assert_in_order(out):
	"""Every section header present, in order (each searched after the one before)."""
	at = 0
	for h in HEADERS:
		at = out.index(h, at)


def _report(**over):
	r = {
		"company": "",
		"warehouse": "Main Branch",
		"report_no": "POS-CLO-1",
		"period_start": "2026-10-31 08:00:00",
		"period_end": "2026-10-31 18:00:00",
		"printed_at": "2026-10-31 18:05:00",
		"tax_id": "P051234567X",
		"pos_profile": "Till 1",
		"cashier": "a@x.com",
		"cashier_name": "Amina",
		"printed_by": "m@x.com",
		"printed_by_name": "Manager Mo",
		"first_doc": "SINV-1",
		"last_doc": "SINV-9",
		"sales_count": 9,
		"users": [
			{
				"user": "a@x.com",
				"full_name": "Amina Very Long Cashier Name",
				"total": 900.0,
				"modes": [{"mode": "Cash", "amount": 900.0}],
			}
		],
		"tenders": [{"mode": "Cash", "amount": 900.0}],
		"tender_total": 900.0,
		"credit_collected": [{"mode": "M-Pesa", "amount": 100.0}],
		"credit_total": 100.0,
		"returns": {"count": 1, "modes": [{"mode": "Cash", "amount": -50.0}], "total": -50.0},
		"refund_total": 0.0,
		"discount_total": 10.0,
		"taxes": [{"description": "VAT 16% included in the price of goods", "amount": 124.0}],
		"net_total": 776.0,
		"tax_total": 124.0,
		"grand_total": 900.0,
		"expenses": [
			{
				"name": "JV-1",
				"label": "Newspaper",
				"note": "",
				"amount": 20.0,
				"user": "a@x.com",
				"user_name": "Amina",
				"pending": True,
			}
		],
		"expense_total": 20.0,
		"cash_position": [
			{
				"mode": "Cash",
				"opening": 100.0,
				"in": 900.0,
				"out": 20.0,
				"expected": 980.0,
				"counted": None,
				"difference": None,
			}
		],
		"total_balance": 980.0,
		"outstanding": [],
		"excluded_invoices": 0,
		"excluded_payment_entries": 0,
	}
	r.update(over)
	return r


class TestZReportEscpos(FrappeTestCase):
	def test_frame_and_width(self):
		cp = [dict(_report()["cash_position"][0], mode="M" * 50)]
		out = render_escpos(
			_report(
				company="A Rather Long Company Name Trading Limited",
				warehouse="Warehouse " * 6,
				cash_position=cp,
				excluded_invoices=2,
				excluded_payment_entries=1,
				expenses=[dict(_report()["expenses"][0], note="paid the vendor " * 6)],
				users=[dict(_report()["users"][0], on_credit=123456789.0)],
				on_credit_total=123456789.0,
				written_off_total=5.0,
			),
			width=42,
		)
		self.assertTrue(out.startswith("\x1b@\x1c\x2e\x1b\x74\x00"))
		self.assertTrue(out.endswith("\x1b\x64\x04\x1d\x56\x00"))
		for ln in out.split("\n"):
			text = re.sub(r"\x1b@|\x1b[atdE].|\x1d..|\x1c.", "", ln)
			self.assertLessEqual(len(text), 42, ln)
			if "\x1d\x21\x10" in ln:
				self.assertLessEqual(len(text), 21, ln)
		self.assertNotIn("\x1d\x21\x01", out)
		self.assertNotIn("\x1d\x21\x11", out)

	def test_sections_in_order(self):
		out = render_escpos(_report())
		_assert_in_order(out)

	def test_pending_expense(self):
		self.assertIn("(awaiting approval)", render_escpos(_report()))

	def test_expense_shows_who_and_note(self):
		out = render_escpos(_report(expenses=[dict(_report()["expenses"][0], note="for the shop")]), width=42)
		self.assertIn("  Amina: for the shop", out)

	def test_tax_total_and_labels(self):
		out = render_escpos(_report(), width=42)
		self.assertIn("Tax total", out)
		self.assertIn("Discounts (net of returns)", out)
		self.assertNotIn("On credit", out)  # zero: not printed
		self.assertNotIn("Written off", out)
		out = render_escpos(_report(on_credit_total=40.0, written_off_total=5.0), width=42)
		self.assertIn("On credit (not in totals)", out)
		self.assertIn("Written off", out)

	def test_escpos_needs_print_permission_on_the_closing(self):
		from klik_pos.z_report import z_report_escpos

		closing = frappe.get_all(
			"POS Closing Entry", {"docstatus": 1}, ["name", "pos_opening_entry"], limit=1
		)
		if not closing:
			raise unittest.SkipTest("no submitted POS Closing Entry on this site")
		opening = closing[0].pos_opening_entry
		frappe.set_user("Administrator")
		self.assertTrue(z_report_escpos(opening).startswith("\x1b@"))
		email = "z-report-noprint@example.com"
		self.addCleanup(_drop_user, email)
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZNoPrint", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		user.add_roles("Sales User")
		frappe.set_user(email)
		self.assertFalse(frappe.has_permission("POS Closing Entry", "print", doc=closing[0].name))
		with self.assertRaises(frappe.PermissionError):
			z_report_escpos(opening)

		# QZ's print agent renders queued jobs with ignore_print_permissions set: allowed.
		self.addCleanup(
			setattr, frappe.flags, "ignore_print_permissions", frappe.flags.ignore_print_permissions
		)
		frappe.flags.ignore_print_permissions = True
		self.assertTrue(z_report_escpos(opening).startswith("\x1b@"))

	def test_counted_and_diff_only_when_counted(self):
		self.assertNotIn("Counted", render_escpos(_report()))
		self.assertNotIn("Diff", render_escpos(_report()))
		cp = [dict(_report()["cash_position"][0], counted=970.0, difference=-10.0)]
		out = render_escpos(_report(cash_position=cp))
		self.assertIn("Counted", out)
		self.assertIn("Diff", out)

	def test_not_counted_line_only_when_excluded(self):
		self.assertNotIn("Not counted", render_escpos(_report()))
		self.assertIn(
			"Not counted: 2 invoices, 1 payments",
			render_escpos(_report(excluded_invoices=2, excluded_payment_entries=1)),
		)

	def test_empty_report(self):
		out = render_escpos(
			_report(
				users=[],
				tenders=[],
				credit_collected=[],
				taxes=[],
				expenses=[],
				cash_position=[],
				returns={"count": 0, "modes": [], "total": 0},
				first_doc=None,
				last_doc=None,
				sales_count=0,
				discount_total=0.0,
				net_total=0.0,
				tax_total=0.0,
				grand_total=0.0,
				tax_id=None,
			)
		)
		kept = ("Z REPORT", "Tender types", "Total balance")
		for h in HEADERS:
			(self.assertIn if h in kept else self.assertNotIn)(h, out)


class TestZReportSkipsZeros(FrappeTestCase):
	"""A zero line or an all-zero section is not printed, on either format."""

	def zeros(self):
		base = _report()
		cash = dict(base["cash_position"][0], opening=0.0, counted=980.0, difference=0.0)
		idle = dict(
			base["cash_position"][0], mode="Cheque", opening=0.0, expected=0.0, counted=0.0, difference=0.0
		)
		idle["in"] = idle["out"] = 0.0
		return _report(
			users=[base["users"][0], dict(base["users"][0], full_name="Idle Ida", total=0.0, modes=[])],
			tenders=[*base["tenders"], {"mode": "Bank Draft", "amount": 0.0}],
			credit_collected=[{"mode": "M-Pesa", "amount": 0.0}],
			credit_total=0.0,
			returns={"count": 0, "modes": [{"mode": "Cash", "amount": 0.0}], "total": 0.0},
			discount_total=0.0,
			expenses=[],
			expense_total=0.0,
			cash_position=[cash, idle],
		)

	def check(self, out):
		for gone in (
			"Bank Draft",
			"Idle Ida",
			"Credit collected",
			"Returns",
			"Discounts",
			"Expenses",
			"Cheque",
			"Opening",
			"Diff",
		):
			self.assertNotIn(gone, out)
		for kept in (
			"Sales by user",
			"Tender types",
			"Tax",
			"Cash position",
			"Expected",
			"Counted",
			"In",
			"Out",
			"Total balance",
		):
			self.assertIn(kept, out)

	def test_escpos(self):
		self.check(render_escpos(self.zeros(), width=42))

	def test_html(self):
		self.check(render_html(self.zeros()))


class TestZReportHeader(FrappeTestCase):
	def test_escpos_header(self):
		out = render_escpos(_report(), width=42)
		for text in (
			"Tax ID",
			"P051234567X",
			"Till",
			"Till 1",
			"Cashier",
			"Amina",
			"Opened",
			"Closed",
			"Printed by",
			"Manager Mo",
			"Printed on",
		):
			self.assertIn(text, out)
		out = render_escpos(_report(tax_id=None, pos_profile=None, cashier=None, cashier_name=None))
		self.assertNotIn("Tax ID", out)
		self.assertNotIn("Till", out)
		self.assertNotIn("\nCashier ", out)

	def test_printed_by_is_the_print_jobs_owner_under_qz(self):
		from klik_pos.z_report import _printed_by

		if not frappe.db.exists("DocType", "Print Job"):
			raise unittest.SkipTest("cecypo_qz_extension is not installed")
		closing = frappe.get_all("POS Closing Entry", {"docstatus": 1}, pluck="name", limit=1)
		if not closing:
			raise unittest.SkipTest("no submitted POS Closing Entry on this site")
		self.assertEqual(_printed_by(closing[0]), frappe.session.user)  # preview / browser print
		job = frappe.get_doc(
			{
				"doctype": "Print Job",
				"reference_doctype": "POS Closing Entry",
				"reference_name": closing[0],
				"status": "Queued",
			}
		).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		frappe.db.set_value("Print Job", job.name, "owner", "requester@example.com", update_modified=False)
		self.addCleanup(frappe.delete_doc, "Print Job", job.name, force=True, ignore_permissions=True)
		self.addCleanup(
			setattr, frappe.flags, "ignore_print_permissions", frappe.flags.ignore_print_permissions
		)
		frappe.flags.ignore_print_permissions = True  # how QZ's agent renders a queued job
		self.assertEqual(_printed_by(closing[0]), "requester@example.com")


class TestZReportHtml80(FrappeTestCase):
	def test_header_and_sections(self):
		out = render_html(_report())
		for text in (
			"P051234567X",
			"Till 1",
			"Amina",
			"Manager Mo",
			"2026-10-31 08:00",
			"2026-10-31 18:00",
			"900.00",
			"awaiting approval",
			"Tax total",
		):
			self.assertIn(text, out)
		_assert_in_order(out)
		self.assertNotIn("Counted", out)
		cp = [dict(_report()["cash_position"][0], counted=970.0, difference=-10.0)]
		self.assertIn("Counted", render_html(_report(cash_position=cp)))

	def test_escaped(self):
		evil = "<script>alert(1)</script>"
		out = render_html(_report(company=evil, cashier_name=evil, tax_id=evil))
		self.assertNotIn("<script>", out)
		self.assertIn("&lt;script&gt;", out)

	def test_html_gate_matches_escpos(self):
		from klik_pos.z_report import z_report_html

		closing = frappe.get_all(
			"POS Closing Entry", {"docstatus": 1}, ["name", "pos_opening_entry"], limit=1
		)
		if not closing:
			raise unittest.SkipTest("no submitted POS Closing Entry on this site")
		frappe.set_user("Administrator")
		self.assertIn("Z REPORT", z_report_html(closing[0].pos_opening_entry))
		email = "z-report-noprint@example.com"
		self.addCleanup(_drop_user, email)
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZNoPrint", "send_welcome_email": 0}
		).insert(ignore_permissions=True).add_roles("Sales User")
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			z_report_html(closing[0].pos_opening_entry)

	def test_print_format_renders(self):
		closing = frappe.get_all("POS Closing Entry", {"docstatus": 1}, pluck="name", limit=1)
		if not closing:
			raise unittest.SkipTest("no submitted POS Closing Entry on this site")
		frappe.set_user("Administrator")
		html = frappe.get_print("POS Closing Entry", closing[0], "Z Report")
		self.assertIn("Z REPORT", html)
		self.assertIn("Cash position", html)


class TestZReportNeedsKlik(FrappeTestCase):
	def test_shift_scope_refuses_without_klik_columns(self):
		from unittest.mock import patch

		opening = frappe.get_all("POS Opening Entry", pluck="name", limit=1)
		if not opening:
			raise unittest.SkipTest("no POS Opening Entry on this site")
		with (
			patch("klik_pos.z_report._has", return_value=False),
			self.assertRaisesRegex(frappe.ValidationError, "klik_pos"),
		):
			build_z_report(opening_entry=opening[0])
