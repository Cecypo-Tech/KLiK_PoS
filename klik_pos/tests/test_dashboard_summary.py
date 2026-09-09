"""The dashboard's numbers must balance, and must not depend on how many rows were fetched.

Three properties are pinned here, because all three were broken on the page this endpoint
replaces:

1. Every submitted invoice in scope is counted - the old page summed the 100 most recently
   modified invoices, so a busy till saw an arbitrary total rather than a slightly wrong one.
2. Credit sales are money too. Credit carries no `Sales Invoice Payment` rows, so it was in
   headline revenue and absent from the payment breakdown; the identity below is what makes
   that impossible to reintroduce.
3. Money collected after the sale, through a Payment Entry, is attributed to the invoice's
   range and only for the amount actually allocated to it.

The invoices are seeded into a date window years away from any real data on the site, and
the window is asserted empty before seeding - a shared dev site is exactly where a test
that quietly measures somebody else's invoices passes while proving nothing.

Credit and return invoices are created as ordinary Sales Invoices with the POS profile
stamped on afterwards. Writing them through the POS builder would test the checkout, not
the aggregation, and would drag the profile's partial-payment flag into a test that has
nothing to do with it.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.dashboard import get_dashboard_summary

COMPANY = "Dev Co"
PROFILE = "_Test POS Profile"
ITEM = "Consulting"
CUSTOMER = "Walk In"

# Far from any real posting date on a dev or staging site, and from the other test modules.
DAY_ONE = "2019-03-04"
DAY_TWO = "2019-03-05"
OUTSIDE = "2019-04-20"


def _payable(doc) -> float:
	"""What the customer owes: the rounded total where rounding applies, else the grand total."""
	if not doc.disable_rounded_total and flt(doc.base_rounded_total):
		return flt(doc.base_rounded_total)
	return flt(doc.base_grand_total)


def _invoice(posting_date, lines, shares=None, is_pos=True, is_return=0, return_against=None):
	"""A submitted invoice for the till.

	`shares` splits the payable total across the POS Profile's own payment rows, in order.
	The modes are not named here on purpose: ERPNext's set_pos_fields rebuilds `payments`
	from the profile during set_missing_values, so any row appended beforehand is discarded
	and a fixture that names its modes silently tests different ones than it claims.
	"""
	si = frappe.new_doc("Sales Invoice")
	si.customer = CUSTOMER
	si.company = COMPANY
	si.set_posting_time = 1
	si.posting_date = posting_date
	si.posting_time = "10:15:00"
	si.is_return = is_return
	si.return_against = return_against
	si.is_pos = 1 if is_pos else 0
	if is_pos:
		si.pos_profile = PROFILE
	for qty, rate in lines:
		si.append("items", {"item_code": ITEM, "qty": qty, "rate": rate})
	si.set_missing_values()
	si.calculate_taxes_and_totals()

	if shares:
		if len(si.payments) < len(shares):
			raise AssertionError(
				f"{PROFILE} offers {len(si.payments)} payment modes; the fixture needs {len(shares)}"
			)
		total = flt(si.rounded_total or si.grand_total)
		for row in si.payments:
			row.amount = 0
		for row, share in zip(si.payments, shares, strict=False):
			row.amount = flt(total * share, 2)
		# Absorb rounding on the last funded row so the invoice is exactly settled.
		si.payments[len(shares) - 1].amount += total - sum(flt(p.amount) for p in si.payments)
	elif si.payments:
		for row in si.payments:
			row.amount = 0

	si.insert(ignore_permissions=True)
	si.submit()
	if not is_pos:
		# Deni and returns still belong to the till that rang them.
		frappe.db.set_value("Sales Invoice", si.name, "pos_profile", PROFILE, update_modified=False)
	si.reload()
	return si


def _settle(invoice, amount, mode):
	"""Collect an existing debt later, the way the customer-payment flow does."""
	receivable, cash, currency = frappe.db.get_value(
		"Company", COMPANY, ["default_receivable_account", "default_cash_account", "default_currency"]
	)
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.party_type = "Customer"
	pe.party = invoice.customer
	pe.company = COMPANY
	pe.posting_date = DAY_TWO
	pe.mode_of_payment = mode
	pe.paid_from = receivable
	pe.paid_to = cash
	pe.paid_amount = pe.received_amount = amount
	pe.source_exchange_rate = pe.target_exchange_rate = 1
	pe.paid_from_account_currency = pe.paid_to_account_currency = currency
	pe.append(
		"references",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"allocated_amount": amount,
		},
	)
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe


def _summary(**kwargs):
	params = {
		"company": COMPANY,
		"pos_profiles": [PROFILE],
		"date_range": "custom",
		"date_from": DAY_ONE,
		"date_to": DAY_TWO,
	}
	params.update(kwargs)
	return get_dashboard_summary(**params)


class TestDashboardSummary(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		baseline = _summary()
		if baseline["identity"]["billed"] or baseline["identity"]["credit"]:
			raise AssertionError(
				f"the seed window {DAY_ONE}..{DAY_TWO} already holds invoices "
				f"({baseline['identity']}); every expectation below would be measuring them too"
			)

		# Two lines each throughout: a per-line fanout in any of the header sums would double
		# these figures, which is the bug this endpoint was written to stop repeating.
		cls.cash = _invoice(DAY_ONE, [(2, 100), (1, 50)], shares=[1.0])
		cls.split = _invoice(DAY_ONE, [(1, 200), (2, 25)], shares=[0.4, 0.6])
		cls.day_two = _invoice(DAY_TWO, [(3, 30), (1, 10)], shares=[1.0])

		cls.credit_sale = _invoice(DAY_ONE, [(1, 300), (1, 100)], is_pos=False)
		cls.settled_later = _invoice(DAY_TWO, [(1, 500), (1, 100)], is_pos=False)
		cls.later_payment = _settle(cls.settled_later, 250, "Cheque")

		cls.refund_owed = _invoice(
			DAY_TWO, [(-1, 100)], is_pos=False, is_return=1, return_against=cls.cash.name
		)

		# Must never be counted: not submitted, cancelled, or outside the window.
		cls.draft = frappe.new_doc("Sales Invoice")
		cls.draft.update(
			{
				"customer": CUSTOMER,
				"company": COMPANY,
				"is_pos": 1,
				"pos_profile": PROFILE,
				"set_posting_time": 1,
				"posting_date": DAY_ONE,
			}
		)
		cls.draft.append("items", {"item_code": ITEM, "qty": 1, "rate": 9999})
		cls.draft.append("payments", {"mode_of_payment": "Cash", "amount": 0})
		cls.draft.insert(ignore_permissions=True)

		cls.cancelled = _invoice(DAY_ONE, [(1, 777)], shares=[1.0])
		cls.cancelled.cancel()

		cls.outside = _invoice(OUTSIDE, [(1, 4242)], shares=[1.0])

		for doc in (cls.cash, cls.split, cls.day_two, cls.credit_sale, cls.settled_later, cls.refund_owed):
			doc.reload()

		cls.summary = _summary()

	# -- the identity ------------------------------------------------------------------

	def test_the_identity_balances(self):
		"""The one line on the page that must always be true."""
		self.assertEqual(self.summary["identity"]["unexplained"], 0.0)

	def test_billed_counts_every_submitted_invoice_in_the_window(self):
		expected = sum(
			_payable(doc)
			for doc in (self.cash, self.split, self.day_two, self.credit_sale, self.settled_later, self.refund_owed)
		)

		self.assertAlmostEqual(self.summary["identity"]["billed"], flt(expected, 2), places=2)

	def test_a_credit_sale_is_reported_as_credit(self):
		identity = self.summary["identity"]
		expected = _payable(self.credit_sale) + (_payable(self.settled_later) - 250)

		self.assertAlmostEqual(identity["credit"], flt(expected, 2), places=2)
		self.assertEqual(identity["credit_invoices"], 2)

	def test_money_collected_later_is_credited_to_the_invoice_s_range(self):
		identity = self.summary["identity"]

		self.assertAlmostEqual(identity["collected_later"], 250.0, places=2)
		cheque = next(row for row in self.summary["collected_by_mode"] if row["mode"] == "Cheque")
		self.assertAlmostEqual(cheque["later"], 250.0, places=2)
		self.assertEqual(cheque["amount"], 0.0)

	def test_an_unpaid_refund_is_owed_not_collected(self):
		identity = self.summary["identity"]

		self.assertAlmostEqual(identity["refunds_owed"], abs(_payable(self.refund_owed)), places=2)
		self.assertEqual(identity["returns"], 1)
		self.assertAlmostEqual(identity["returns_total"], _payable(self.refund_owed), places=2)

	def test_the_mode_rows_sum_to_what_was_collected(self):
		identity = self.summary["identity"]
		rows = self.summary["collected_by_mode"]

		self.assertAlmostEqual(
			sum(row["amount"] for row in rows), identity["collected_at_sale"], places=2
		)
		self.assertAlmostEqual(sum(row["later"] for row in rows), identity["collected_later"], places=2)

	def test_a_sale_settled_by_a_payment_entry_is_counted_once_for_its_mode(self):
		"""M-Pesa carries its mode on a zero-amount payment row and its money on a Payment
		Entry stamped with the shift. Both queries then land on the same mode row, and
		counting the placeholder as a sale of its own turns one sale into two.

		The placeholder is planted here because ERPNext's on_submit deletes zero-amount rows
		today: how many sales a mode row claims must be a property of this reader, not of
		what some other app's on_submit happens to tidy up.
		"""
		# The sale is settled after it is rung up, exactly as the M-Pesa flow settles one;
		# the flag only says the till may ring it up that way.
		partial = frappe.db.get_value("POS Profile", PROFILE, "allow_partial_payment")
		frappe.db.set_value("POS Profile", PROFILE, "allow_partial_payment", 1)
		self.addCleanup(frappe.db.set_value, "POS Profile", PROFILE, "allow_partial_payment", partial)
		mode = frappe.get_doc("POS Profile", PROFILE).payments[0].mode_of_payment
		before = _summary()
		before_row = next(r for r in before["collected_by_mode"] if r["mode"] == mode)

		settled_by_entry = _invoice(DAY_TWO, [(1, 40)])  # every payment row zero
		payable = _payable(settled_by_entry)
		stamped = _settle(settled_by_entry, payable, mode)
		frappe.db.set_value(
			"Payment Entry", stamped.name, "custom_pos_opening_entry", "POS-OPE-ADVANCE", update_modified=False
		)
		frappe.get_doc(
			{
				"doctype": "Sales Invoice Payment",
				"parent": settled_by_entry.name,
				"parenttype": "Sales Invoice",
				"parentfield": "payments",
				"idx": 1,
				"docstatus": 1,
				"mode_of_payment": mode,
				"amount": 0,
				"base_amount": 0,
			}
		).db_insert()

		summary = _summary()

		row = next(r for r in summary["collected_by_mode"] if r["mode"] == mode)
		self.assertEqual(row["count"], before_row["count"] + 1, "the placeholder counted the sale twice")
		self.assertAlmostEqual(row["amount"], before_row["amount"] + payable, places=2)
		self.assertEqual(summary["identity"]["unexplained"], 0.0)

	def test_a_split_payment_lands_on_every_mode_it_used(self):
		"""Two modes on one invoice must appear as two rows, each carrying its own share."""
		rows = {row["mode"]: row for row in self.summary["collected_by_mode"]}
		funded = [row for row in self.split.payments if flt(row.amount)]

		self.assertEqual(len(funded), 2, "the split fixture stopped splitting")
		for payment in funded:
			self.assertIn(payment.mode_of_payment, rows)

		# Only the split invoice used the second mode, so that row is its share exactly.
		second = funded[1]
		self.assertAlmostEqual(rows[second.mode_of_payment]["amount"], flt(second.amount, 2), places=2)
		self.assertEqual(rows[second.mode_of_payment]["count"], 1)

		# Cash was the first mode on all three paid invoices.
		self.assertEqual(rows[funded[0].mode_of_payment]["count"], 3)

	# -- scope -------------------------------------------------------------------------

	def test_drafts_and_cancelled_invoices_are_not_money(self):
		"""9,999 and 777 are loud enough that either leaking in would move every total."""
		self.assertNotIn(9999.0, [self.summary["identity"]["billed"]])
		names = [row["name"] for row in self.summary["performance"]["recent"]]

		self.assertNotIn(self.draft.name, names)
		self.assertNotIn(self.cancelled.name, names)

	def test_an_invoice_outside_the_window_is_outside_the_answer(self):
		self.assertNotIn(
			self.outside.name, [row["name"] for row in self.summary["performance"]["recent"]]
		)

	def test_narrowing_to_one_day_narrows_the_money(self):
		day_one = _summary(date_to=DAY_ONE)
		expected = sum(_payable(doc) for doc in (self.cash, self.split, self.credit_sale))

		self.assertAlmostEqual(day_one["identity"]["billed"], flt(expected, 2), places=2)
		self.assertEqual(day_one["identity"]["unexplained"], 0.0)

	def test_the_window_is_reported_back(self):
		scope = self.summary["scope"]

		self.assertEqual(scope["range"], "custom")
		self.assertEqual(scope["date_from"], DAY_ONE)
		self.assertEqual(scope["date_to"], DAY_TWO)
		self.assertEqual(scope["pos_profiles"], [PROFILE])
		self.assertIsNone(scope["fallback"])

	# -- performance -------------------------------------------------------------------

	def test_the_kpis_are_the_same_numbers_as_the_hero(self):
		kpis = self.summary["performance"]["kpis"]
		identity = self.summary["identity"]

		self.assertAlmostEqual(kpis["revenue"], identity["billed"], places=2)
		self.assertEqual(kpis["invoices"], identity["invoices"])
		self.assertAlmostEqual(kpis["average"], flt(kpis["revenue"] / kpis["invoices"], 2), places=2)

	def test_the_hourly_buckets_add_up_to_the_day(self):
		hourly = self.summary["performance"]["hourly"]

		self.assertAlmostEqual(
			sum(bucket["amount"] for bucket in hourly), self.summary["identity"]["billed"], places=2
		)

	def test_top_items_are_ranked_and_capped(self):
		top = self.summary["performance"]["top_items"]

		self.assertLessEqual(len(top), 5)
		self.assertEqual([row["amount"] for row in top], sorted((r["amount"] for r in top), reverse=True))

	def test_money_taken_at_the_till_as_a_payment_entry_is_at_sale_not_later(self):
		"""M-Pesa now settles through Payment Entries stamped with the shift; the reader
		took that money at the counter and the hero must say so - on the right mode row."""
		before = _summary()
		cash_before = next(row for row in before["collected_by_mode"] if row["mode"] == "Cash")["amount"]

		stamped = _settle(self.settled_later, 100, "Cash")
		frappe.db.set_value("Payment Entry", stamped.name, "custom_pos_opening_entry", "POS-OPE-STAMPED", update_modified=False)

		summary = _summary()

		cash = next(row for row in summary["collected_by_mode"] if row["mode"] == "Cash")
		self.assertAlmostEqual(cash["amount"], cash_before + 100.0, places=2)
		self.assertAlmostEqual(summary["identity"]["collected_later"], before["identity"]["collected_later"], places=2)
		self.assertEqual(summary["identity"]["unexplained"], 0.0)


class TestDashboardSummaryScopeAndPermissions(FrappeTestCase):
	def test_an_unknown_range_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			get_dashboard_summary(company=COMPANY, date_range="fortnight")

	def test_a_custom_range_needs_both_ends(self):
		with self.assertRaises(frappe.ValidationError):
			get_dashboard_summary(company=COMPANY, date_range="custom", date_from=DAY_ONE)

	def test_a_backwards_custom_range_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			get_dashboard_summary(
				company=COMPANY, date_range="custom", date_from=DAY_TWO, date_to=DAY_ONE
			)

	def test_a_year_to_date_range_is_allowed(self):
		"""The cap guards the database, not the reader's questions; a year must fit."""
		summary = get_dashboard_summary(
			company=COMPANY, date_range="custom", date_from="2019-01-01", date_to="2019-12-31"
		)

		self.assertEqual(summary["scope"]["date_from"], "2019-01-01")

	def test_a_custom_range_longer_than_a_year_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			get_dashboard_summary(
				company=COMPANY, date_range="custom", date_from="2018-01-01", date_to="2019-12-31"
			)

	def test_a_profile_of_another_company_is_refused_not_dropped(self):
		"""Silently narrowing the scope is how a total nobody can explain gets onto the page."""
		with self.assertRaises(frappe.ValidationError):
			get_dashboard_summary(company=COMPANY, pos_profiles=["No Such Till"], date_range="today")

	def test_profiles_may_arrive_as_a_json_string(self):
		"""The SPA sends a query string, so the list arrives encoded."""
		summary = get_dashboard_summary(
			company=COMPANY, pos_profiles=f'["{PROFILE}"]', date_range="custom",
			date_from=DAY_ONE, date_to=DAY_TWO,
		)

		self.assertEqual(summary["scope"]["pos_profiles"], [PROFILE])

	def test_a_user_without_a_dashboard_role_is_refused(self):
		with patch("frappe.get_roles", return_value=["All", "Sales User"]):
			with self.assertRaises(frappe.PermissionError):
				get_dashboard_summary(company=COMPANY, date_range="today")

	def test_a_manager_may_not_read_another_company(self):
		with patch("frappe.get_roles", return_value=["All", "Sales Manager"]):
			with patch("frappe.defaults.get_user_default", return_value=COMPANY):
				with self.assertRaises(frappe.PermissionError):
					get_dashboard_summary(company="Some Other Co", date_range="today")

	def test_a_system_manager_may_name_any_company(self):
		"""Refused for not existing, not for being somebody else's - the check that ran matters."""
		with patch("frappe.get_roles", return_value=["All", "System Manager"]):
			with patch("frappe.defaults.get_user_default", return_value=COMPANY):
				with self.assertRaises(frappe.ValidationError):
					get_dashboard_summary(company="Some Other Co", date_range="today")

	def test_shift_falls_back_to_today_and_says_so(self):
		"""A till with nothing open still deserves an answer, clearly labelled."""
		with patch("klik_pos.api.dashboard.frappe.get_all", side_effect=_no_open_shifts):
			summary = get_dashboard_summary(company=COMPANY, date_range="shift")

		self.assertEqual(summary["scope"]["fallback"], "today")
		self.assertEqual(summary["scope"]["date_from"], frappe.utils.nowdate())


def _no_open_shifts(doctype, *args, **kwargs):
	"""Every other get_all call behaves; POS Opening Entry returns nothing."""
	if doctype == "POS Opening Entry":
		return []
	return _real_get_all(doctype, *args, **kwargs)


_real_get_all = frappe.get_all


def _draft_invoice(queue_status, pos_profile=PROFILE):
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": CUSTOMER,
			"company": COMPANY,
			"is_pos": 1,
			"pos_profile": PROFILE,
			"set_posting_time": 1,
			"posting_date": DAY_ONE,
		}
	)
	si.append("items", {"item_code": ITEM, "qty": 1, "rate": 10})
	si.insert(ignore_permissions=True)
	# Written at DB level so a till that no longer exists can be stamped on: that is exactly
	# the state a renamed or deleted POS Profile leaves its unfinished sales in.
	frappe.db.set_value(
		"Sales Invoice",
		si.name,
		{"queue_status": queue_status, "pos_profile": pos_profile},
		update_modified=False,
	)
	si.reload()
	return si


def _held_order(hours_old):
	so = frappe.new_doc("Sales Order")
	so.customer = CUSTOMER
	so.company = COMPANY
	so.transaction_date = frappe.utils.nowdate()
	so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 1)
	so.append("items", {"item_code": ITEM, "qty": 1, "rate": 10, "delivery_date": so.delivery_date})
	so.insert(ignore_permissions=True)
	frappe.db.set_value(
		"Sales Order",
		so.name,
		{"custom_is_klik_held": 1, "modified": frappe.utils.add_to_date(None, hours=-hours_old)},
		update_modified=False,
	)
	return so


def _exception_counts():
	rows = _summary()["exceptions"]
	return {row["key"]: row["count"] for row in rows}


class TestDashboardExceptions(FrappeTestCase):
	"""What needs attention, counted as a delta.

	A dev or staging site already carries stale held orders and shifts somebody left open;
	asserting absolute counts here would pin this test to that mess and fail the first time
	anybody cleaned it up. The counts are deliberately neither date-scoped nor till-scoped in
	the endpoint - a submission that failed on Friday is still unresolved on Monday, and a
	sale stranded on a till that was since renamed is the one most likely to be forgotten.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.before = _exception_counts()

		cls.failed = _draft_invoice("Failed")
		cls.queued = _draft_invoice("Queued")
		cls.processing = _draft_invoice("Processing")
		cls.stale_hold = _held_order(hours_old=5)
		cls.fresh_hold = _held_order(hours_old=0)
		# The regression: a till that is gone from the POS Profile list entirely.
		cls.orphaned = _draft_invoice("Failed", pos_profile=f"Deleted Till {frappe.generate_hash(length=6)}")

		cls.after = _exception_counts()

	def _delta(self, key):
		return self.after.get(key, 0) - self.before.get(key, 0)

	def test_a_failed_submission_is_reported(self):
		"""Two: one on a live till, one stranded on a till that no longer exists."""
		self.assertEqual(self._delta("failed_submissions"), 2)

	def test_work_stranded_on_a_deleted_till_is_still_counted(self):
		"""The strip answers for the shop, not for the tills the reader happened to pick.

		Scoped per-till, this draft was invisible on the dashboard while Invoice History
		listed it - which is how six queued drafts sat unnoticed on dev behind a POS Profile
		that had been deleted.
		"""
		narrowed = _summary(pos_profiles=[PROFILE])
		counts = {row["key"]: row["count"] for row in narrowed["exceptions"]}

		self.assertNotIn(
			self.orphaned.pos_profile, narrowed["scope"]["pos_profiles"], "fixture is not orphaned"
		)
		self.assertEqual(counts.get("failed_submissions", 0) - self.before.get("failed_submissions", 0), 2)
		self.assertTrue(narrowed["exceptions_cover_company"])

	def test_queued_and_processing_are_counted_together(self):
		"""Both mean the same thing to the reader: a sale the server has not finished."""
		self.assertEqual(self._delta("queued_submissions"), 2)

	def test_a_shift_left_open_on_our_till_counts_whatever_company_it_names(self):
		"""Dev carries two open entries on a Dev Co till stamped with another company.

		Reading the company field alone drops them, which would tell an owner that nothing is
		open on a counter that plainly has a shift running.
		"""
		counts = {row["key"]: row["count"] for row in _summary()["exceptions"]}
		open_on_our_tills = frappe.db.count(
			"POS Opening Entry",
			{
				"status": "Open",
				"docstatus": 1,
				"pos_profile": PROFILE,
				"period_start_date": ["<", frappe.utils.nowdate()],
			},
		)

		self.assertGreaterEqual(counts.get("shifts_open_past_today", 0), open_on_our_tills)

	def test_only_a_forgotten_hold_counts(self):
		self.assertEqual(self._delta("stale_held_orders"), 1)

	def test_every_row_says_where_to_go(self):
		by_key = {row["key"]: row for row in _summary()["exceptions"]}

		for key in ("failed_submissions", "queued_submissions", "stale_held_orders"):
			self.assertIsNotNone(by_key[key]["link"], f"{key} has nowhere to go")
			self.assertTrue(by_key[key]["link"]["route"])

	def test_a_clean_scope_reports_nothing_rather_than_zeroes(self):
		"""Empty means 'All clear' in one line, not a strip of zeroes to read past."""
		for row in _summary()["exceptions"]:
			self.assertGreater(row["count"], 0)


class TestDashboardScopeReporting(FrappeTestCase):
	def test_the_scope_names_every_till_the_reader_could_pick(self):
		"""The till picker is built from this; a second round trip to fill it is not offered."""
		scope = _summary()["scope"]

		self.assertIn(PROFILE, scope["available_profiles"])
		self.assertTrue(set(scope["pos_profiles"]).issubset(set(scope["available_profiles"])))
