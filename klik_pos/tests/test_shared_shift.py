"""One shift per till, joined by every cashier on it.

Each cashier used to open their own POS Opening Entry, even on a shared till, and the close
then counted the whole till's sales for each of them. A till now runs one shift: the first
cashier opens it, the others join it, and whoever closes it closes it for everyone.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import shift
from klik_pos.api.pos_entry import create_closing_entry, current_shift_state, open_pos, opening_conflict
from klik_pos.api.sales_invoice import (
	QUEUE_STATUSES,
	_needs_shift_check,
	get_current_pos_opening_entry,
	retry_failed_sales_invoice,
	submit_draft_invoice,
)
from klik_pos.tests.test_opening_conflict import COMPANY, _profile, _shift, _user

OPENER = "shared-shift-opener@example.com"
JOINER = "shared-shift-joiner@example.com"


def _assign(profile, *users):
	doc = frappe.get_doc("POS Profile", profile)
	for user in users:
		doc.append("applicable_for_users", {"user": user})
	# The fixture profile was inserted with ignore_mandatory; saving it must skip the same checks.
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


class SharedShiftCase(FrappeTestCase):
	def setUp(self):
		_user(OPENER)
		_user(JOINER)
		self.till = _profile()
		_assign(self.till, OPENER, JOINER)
		frappe.defaults.clear_user_default(shift.JOINED_SHIFT_KEY, JOINER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestJoining(SharedShiftCase):
	def test_a_cashier_on_the_till_joins_its_open_shift(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		self.assertEqual(shift.join_shift(self.till), {"success": True, "entry": entry})
		self.assertEqual(get_current_pos_opening_entry(), entry)
		self.assertTrue(open_pos())

	def test_a_cashier_not_on_the_till_cannot_join(self):
		_shift(self.till, OPENER)
		outsider = _user("shared-shift-outsider@example.com")
		frappe.set_user(outsider)

		with self.assertRaises(frappe.PermissionError):
			shift.join_shift(self.till)

	def test_there_is_nothing_to_join_on_a_closed_till(self):
		frappe.set_user(JOINER)
		with self.assertRaises(frappe.ValidationError):
			shift.join_shift(self.till)

	def test_a_joined_shift_that_has_closed_is_forgotten(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		frappe.db.set_value("POS Opening Entry", entry, "status", "Closed")

		self.assertIsNone(get_current_pos_opening_entry())
		self.assertFalse(open_pos())

	def test_my_own_open_shift_wins_over_a_joined_one(self):
		other_till = _profile()
		_assign(other_till, JOINER)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		mine = _shift(other_till, JOINER)

		self.assertEqual(get_current_pos_opening_entry(), mine)

	def test_a_cashier_with_their_own_open_shift_cannot_join_another(self):
		other_till = _profile()
		_assign(other_till, JOINER)
		mine = _shift(other_till, JOINER)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)

		with self.assertRaises(frappe.ValidationError):
			shift.join_shift(self.till)
		self.assertEqual(get_current_pos_opening_entry(), mine)

	def test_joining_a_disabled_till_is_refused(self):
		_shift(self.till, OPENER)
		frappe.db.set_value("POS Profile", self.till, "disabled", 1)
		frappe.set_user(JOINER)

		with self.assertRaises(frappe.ValidationError):
			shift.join_shift(self.till)


class TestOneShiftPerTill(SharedShiftCase):
	def test_another_cashier_s_shift_today_is_offered_to_join(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_open")
		self.assertEqual(conflict["entry"], entry)
		self.assertEqual(conflict["user"], OPENER)

	def test_another_cashier_s_stale_shift_tells_a_cashier_a_manager_is_needed(self):
		"""A cashier may no longer join-and-close another cashier's stale shift themselves."""
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(opening_conflict(self.till)["kind"], "till_needs_manager")

	def test_another_cashier_s_stale_shift_is_offered_to_a_manager_to_close(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			self.assertEqual(opening_conflict(self.till)["kind"], "till_stale")

	def test_a_joined_shift_on_this_till_is_continued(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		conflict = opening_conflict(self.till)
		self.assertEqual((conflict["kind"], conflict["entry"]), ("own_open", entry))

	def test_erpnext_refuses_a_second_shift_on_a_till(self):
		"""klik no longer switches ERPNext's own check off."""
		_shift(self.till, OPENER)
		doc = frappe.new_doc("POS Opening Entry")
		doc.update({"pos_profile": self.till, "user": JOINER, "company": COMPANY})

		with self.assertRaises(frappe.ValidationError):
			doc.check_open_pos_exists()

	def _invoice(self, **overrides):
		"""A klik POS invoice doc, in memory, not inserted."""
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": COMPANY,
				"customer": "Walk In",
				"pos_profile": self.till,
				"is_pos": 1,
				"custom_is_created_from_klik": 1,
			}
		)
		doc.update(overrides)
		return doc

	def _before_submit(self, doc):
		"""Call before_submit with the rest of its body stubbed out, so only the
		shift check under test can raise."""
		with (
			patch.object(type(doc), "validate_reserved_stock_availability"),
			patch.object(type(doc), "validate_full_payment"),
			patch("klik_pos.api.sales_invoice._should_reserve_stock", return_value=False),
		):
			doc.before_submit()

	def test_sales_invoices_use_erpnext_s_own_shift_check(self):
		"""klik must not reimplement ERPNext's shift rule."""
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

		from klik_pos.api.sales_invoice import CustomSalesInvoice

		self.assertIs(CustomSalesInvoice.validate_pos_opening_entry, SalesInvoice.validate_pos_opening_entry)

	def test_before_submit_refuses_a_klik_sale_with_no_open_shift(self):
		frappe.set_user(OPENER)
		doc = self._invoice()

		with self.assertRaises(frappe.ValidationError):
			self._before_submit(doc)

	def test_before_submit_refuses_a_klik_sale_on_a_stale_shift(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)
		doc = self._invoice()

		with self.assertRaises(frappe.ValidationError):
			self._before_submit(doc)

	def test_before_submit_allows_a_klik_sale_on_today_s_shift(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)
		doc = self._invoice()

		self._before_submit(doc)

	def test_before_submit_ignores_the_shift_on_a_return(self):
		frappe.set_user(OPENER)
		doc = self._invoice(is_return=1)

		self._before_submit(doc)

	def test_before_submit_ignores_the_shift_when_not_a_pos_sale(self):
		frappe.set_user(OPENER)
		doc = self._invoice(is_pos=0)

		self._before_submit(doc)

	def test_before_submit_skips_the_check_for_a_queued_worker(self):
		frappe.set_user(OPENER)
		doc = self._invoice()

		frappe.flags.klik_processing_queued_invoice = True
		try:
			self._before_submit(doc)
		finally:
			frappe.flags.klik_processing_queued_invoice = False


from klik_pos.api.pos_entry import _calculate_payment_reconciliation, _get_open_pos_entry


def _paid_invoice(till, entry, owner, amount):
	"""A submitted cash sale stamped with `entry`, written past validation."""
	si = frappe.new_doc("Sales Invoice")
	si.update({"company": COMPANY, "customer": "Walk In", "pos_profile": till,
		"posting_date": frappe.utils.nowdate(), "custom_pos_opening_entry": entry})
	si.append("items", {"item_code": "Consulting", "qty": 1, "rate": amount})
	si.flags.ignore_validate = True
	si.flags.ignore_mandatory = True
	si.insert(ignore_permissions=True)
	si.append("payments", {"mode_of_payment": "Cash", "amount": amount})
	si.db_update_all()
	frappe.db.set_value("Sales Invoice", si.name, {"docstatus": 1, "owner": owner}, update_modified=False)
	frappe.db.sql(
		"update `tabSales Invoice Payment` set docstatus=1, amount=%s where parent=%s", (amount, si.name)
	)
	return si.name


class TestClosingTheTill(SharedShiftCase):
	def test_a_joined_cashier_closes_the_till_s_shift(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)

		self.assertEqual(_get_open_pos_entry(JOINER).name, entry)

	def test_the_close_counts_every_cashier_s_sales_once(self):
		entry = _shift(self.till, OPENER)
		_paid_invoice(self.till, entry, OPENER, 100)
		_paid_invoice(self.till, entry, JOINER, 50)
		# A sale on the same till under an older, different (now closed) shift must not be
		# counted: a real POS Opening Entry, not just a name, so the invoice's link validates.
		older = _shift(self.till, OPENER, status="Closed", days_ago=2)
		_paid_invoice(self.till, older, OPENER, 999)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		opening = _get_open_pos_entry(JOINER)

		rows = _calculate_payment_reconciliation(opening, {"closing_balance": {"Cash": 150}})
		cash = next(r for r in rows if r["mode_of_payment"] == "Cash")

		self.assertEqual(frappe.utils.flt(cash["expected_amount"]), 150)

	def test_closing_forgets_everyone_who_joined(self):
		"""Otherwise cancelling the Closing Entry would silently re-join them all."""
		from klik_pos.api.pos_entry import _forget_joined_users

		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)
		shift.join_shift(self.till)
		self.assertEqual(frappe.defaults.get_user_default(shift.JOINED_SHIFT_KEY, JOINER), entry)

		_forget_joined_users(entry)

		self.assertIsNone(frappe.defaults.get_user_default(shift.JOINED_SHIFT_KEY, JOINER))
		self.assertFalse(
			frappe.db.exists("DefaultValue", {"defkey": shift.JOINED_SHIFT_KEY, "defvalue": entry})
		)


class TestCurrentShiftState(SharedShiftCase):
	def test_own_shift_opened_today_is_not_stale(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(OPENER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(
				current_shift_state(),
				{"entry": entry, "stale": False, "pos_profile": self.till, "manager": False},
			)

	def test_own_shift_opened_yesterday_is_stale(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(OPENER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(
				current_shift_state(),
				{"entry": entry, "stale": True, "pos_profile": self.till, "manager": False},
			)

	def test_a_joined_shift_opened_yesterday_is_stale(self):
		"""A cashier can no longer join another cashier's stale shift (manager-only now);
		a manager still can, and current_shift_state must still report it as stale for them."""
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)
		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			shift.join_shift(self.till)

			self.assertEqual(
				current_shift_state(),
				{"entry": entry, "stale": True, "pos_profile": self.till, "manager": True},
			)

	def test_no_shift_at_all(self):
		frappe.set_user(OPENER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(
				current_shift_state(),
				{"entry": None, "stale": False, "pos_profile": None, "manager": False},
			)


def _klik_pos_doc(till, **overrides):
	"""An in-memory klik POS Sales Invoice, for the pure `_needs_shift_check` truth table."""
	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": COMPANY,
			"customer": "Walk In",
			"pos_profile": till,
			"is_pos": 1,
			"custom_is_created_from_klik": 1,
		}
	)
	doc.update(overrides)
	return doc


class TestNeedsShiftCheck(SharedShiftCase):
	"""The five conditions `_needs_shift_check` gates on, one flipped at a time."""

	def setUp(self):
		super().setUp()
		frappe.flags.klik_processing_queued_invoice = False

	def tearDown(self):
		frappe.flags.klik_processing_queued_invoice = False
		super().tearDown()

	def test_a_klik_pos_sale_needs_the_check(self):
		self.assertTrue(_needs_shift_check(_klik_pos_doc(self.till)))

	def test_not_created_from_klik_is_exempt(self):
		doc = _klik_pos_doc(self.till, custom_is_created_from_klik=0)
		self.assertFalse(_needs_shift_check(doc))

	def test_no_pos_profile_is_exempt(self):
		doc = _klik_pos_doc(self.till, pos_profile=None)
		self.assertFalse(_needs_shift_check(doc))

	def test_not_is_pos_credit_sale_is_exempt(self):
		doc = _klik_pos_doc(self.till, is_pos=0)
		self.assertFalse(_needs_shift_check(doc))

	def test_a_return_is_exempt(self):
		doc = _klik_pos_doc(self.till, is_return=1)
		self.assertFalse(_needs_shift_check(doc))

	def test_the_worker_finishing_a_queued_sale_is_exempt(self):
		doc = _klik_pos_doc(self.till)
		frappe.flags.klik_processing_queued_invoice = True
		self.assertFalse(_needs_shift_check(doc))


class TestQueuePathShiftCheck(SharedShiftCase):
	"""ERPNext's shift check must also run before a sale is queued, not only at submit."""

	def setUp(self):
		super().setUp()
		# submit_draft_invoice runs the invoice's own validate(), which resolves the
		# customer's receivable account - unrelated to the shift check under test, but it
		# needs read permission on Account for a non-Administrator cashier.
		user_doc = frappe.get_doc("User", OPENER)
		if not any(row.role == "Sales User" for row in user_doc.roles):
			user_doc.append("roles", {"role": "Sales User"})
			user_doc.flags.ignore_permissions = True
			user_doc.save()

	def _draft(self, **overrides):
		doc = frappe.new_doc("Sales Invoice")
		doc.update(
			{
				"company": COMPANY,
				"customer": "Walk In",
				"pos_profile": self.till,
				"is_pos": 1,
				"custom_is_created_from_klik": 1,
				"enable_background_invoice_submission": 1,
			}
		)
		doc.append("items", {"item_code": "Consulting", "qty": 1, "rate": 100})
		doc.update(overrides)
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_queuing_on_a_till_with_no_open_shift_is_refused(self):
		frappe.set_user(OPENER)
		invoice_name = self._draft()
		queue_status_before = frappe.db.get_value("Sales Invoice", invoice_name, "queue_status")

		with patch("klik_pos.api.sales_invoice.frappe.enqueue") as mock_enqueue:
			result = submit_draft_invoice(invoice_name)

		self.assertFalse(result["success"])
		mock_enqueue.assert_not_called()
		# Nothing about queueing this sale was left behind: the queue status is exactly
		# what the plain insert gave it (a fresh draft defaults to "Queued" whether or not
		# it is ever actually queued - see the field's default in the custom field
		# fixture), and no Stock Reservation Entry exists for it.
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", invoice_name, "queue_status"), queue_status_before
		)
		self.assertFalse(
			frappe.db.exists("Stock Reservation Entry", {"voucher_no": invoice_name})
		)

	def test_queuing_with_an_open_shift_opened_today_enqueues(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)
		invoice_name = self._draft()

		with patch("klik_pos.api.sales_invoice.frappe.enqueue") as mock_enqueue:
			result = submit_draft_invoice(invoice_name)

		self.assertTrue(result["success"])
		mock_enqueue.assert_called_once()

	def test_retrying_a_failed_invoice_on_a_till_with_no_open_shift_is_refused(self):
		frappe.set_user(OPENER)
		invoice_name = self._draft()
		frappe.db.set_value("Sales Invoice", invoice_name, "queue_status", QUEUE_STATUSES["failed"])

		with patch("klik_pos.api.sales_invoice.frappe.enqueue") as mock_enqueue:
			result = retry_failed_sales_invoice(invoice_name)

		self.assertFalse(result["success"])
		mock_enqueue.assert_not_called()

	def test_retrying_a_failed_invoice_with_an_open_shift_today_enqueues(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)
		invoice_name = self._draft()
		frappe.db.set_value("Sales Invoice", invoice_name, "queue_status", QUEUE_STATUSES["failed"])

		with patch("klik_pos.api.sales_invoice.frappe.enqueue") as mock_enqueue:
			result = retry_failed_sales_invoice(invoice_name)

		self.assertTrue(result["success"])
		mock_enqueue.assert_called_once()


class TestIsShiftManager(SharedShiftCase):
	def test_true_for_each_manager_role(self):
		for role in shift.SHIFT_MANAGER_ROLES:
			with patch("frappe.get_roles", return_value=[role]):
				self.assertTrue(shift.is_shift_manager())

	def test_false_for_a_plain_cashier(self):
		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertFalse(shift.is_shift_manager())


class TestJoinedShiftStaleness(SharedShiftCase):
	def test_a_stale_joined_shift_is_dropped_for_a_cashier(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.defaults.set_user_default(shift.JOINED_SHIFT_KEY, entry, JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertIsNone(shift.joined_shift(JOINER))

	def test_a_stale_joined_shift_is_kept_for_a_manager(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.defaults.set_user_default(shift.JOINED_SHIFT_KEY, entry, JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			self.assertEqual(shift.joined_shift(JOINER), entry)

	def test_a_joined_shift_from_today_is_kept_for_anyone(self):
		entry = _shift(self.till, OPENER)
		frappe.defaults.set_user_default(shift.JOINED_SHIFT_KEY, entry, JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(shift.joined_shift(JOINER), entry)


class TestJoinShiftManagerRules(SharedShiftCase):
	SECOND_OPENER = "shared-shift-second-opener@example.com"

	def setUp(self):
		super().setUp()
		_user(self.SECOND_OPENER)

	def test_a_cashier_on_a_stale_single_shift_till_is_refused(self):
		_shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaisesRegex(frappe.ValidationError, "manager"):
				shift.join_shift(self.till)

	def test_a_manager_on_the_same_till_is_accepted(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			self.assertEqual(shift.join_shift(self.till), {"success": True, "entry": entry})

	def test_a_cashier_on_a_till_with_two_open_shifts_is_refused(self):
		_shift(self.till, OPENER)
		_shift(self.till, self.SECOND_OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaises(frappe.ValidationError):
				shift.join_shift(self.till)

	def test_a_manager_without_entry_on_that_till_is_refused(self):
		"""Even a manager must pick a shift with `entry` when several are open."""
		_shift(self.till, OPENER)
		_shift(self.till, self.SECOND_OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			with self.assertRaises(frappe.ValidationError):
				shift.join_shift(self.till)

	def test_a_manager_with_entry_joins_exactly_that_shift(self):
		older = _shift(self.till, OPENER, days_ago=1)
		_shift(self.till, self.SECOND_OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			result = shift.join_shift(self.till, entry=older)
			self.assertEqual(result, {"success": True, "entry": older})
			self.assertEqual(shift.joined_shift(JOINER), older)

	def test_a_cashier_passing_entry_gets_permission_error(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			with self.assertRaises(frappe.PermissionError):
				shift.join_shift(self.till, entry=entry)

	def test_entry_not_on_the_till_is_a_validation_error(self):
		other_till = _profile()
		_assign(other_till, JOINER)
		elsewhere = _shift(other_till, OPENER)
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			with self.assertRaises(frappe.ValidationError):
				shift.join_shift(self.till, entry=elsewhere)

	def test_entry_not_open_is_a_validation_error(self):
		entry = _shift(self.till, OPENER, status="Closed")
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			with self.assertRaises(frappe.ValidationError):
				shift.join_shift(self.till, entry=entry)

	def test_a_today_single_shift_is_joined_by_a_cashier(self):
		entry = _shift(self.till, OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertEqual(shift.join_shift(self.till), {"success": True, "entry": entry})


class TestOpeningConflictManagerTable(SharedShiftCase):
	SECOND_OPENER = "shared-shift-conflict-second@example.com"

	def setUp(self):
		super().setUp()
		_user(self.SECOND_OPENER)

	def test_multiple_open_shifts_cashier_sees_till_needs_manager(self):
		older = _shift(self.till, OPENER, days_ago=1)
		newer = _shift(self.till, self.SECOND_OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_needs_manager")
		self.assertFalse(conflict["manager"])
		self.assertEqual([row["entry"] for row in conflict["open_shifts"]], [older, newer])

	def test_multiple_open_shifts_manager_sees_till_multiple(self):
		older = _shift(self.till, OPENER, days_ago=1)
		newer = _shift(self.till, self.SECOND_OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_multiple")
		self.assertTrue(conflict["manager"])
		self.assertEqual([row["entry"] for row in conflict["open_shifts"]], [older, newer])

	def test_single_stale_shift_cashier_sees_till_needs_manager(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_needs_manager")
		self.assertFalse(conflict["manager"])
		self.assertEqual(conflict["open_shifts"][0]["entry"], entry)

	def test_single_stale_shift_manager_sees_till_stale(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			conflict = opening_conflict(self.till)

		self.assertEqual(conflict["kind"], "till_stale")
		self.assertTrue(conflict["manager"])
		self.assertEqual(conflict["entry"], entry)

	def test_single_open_shift_today_is_till_open_for_both(self):
		_shift(self.till, OPENER)
		frappe.set_user(JOINER)

		with patch("frappe.get_roles", return_value=["Sales User"]):
			cashier_conflict = opening_conflict(self.till)
		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			manager_conflict = opening_conflict(self.till)

		self.assertEqual(cashier_conflict["kind"], "till_open")
		self.assertEqual(manager_conflict["kind"], "till_open")


class TestClosingRefusesAnotherCashiersStaleShift(SharedShiftCase):
	def _entry_row(self, entry):
		return frappe.db.get_value(
			"POS Opening Entry",
			entry,
			["name", "pos_profile", "company", "period_start_date", "user"],
			as_dict=True,
		)

	def test_a_cashier_cannot_close_someone_elses_stale_shift(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		row = self._entry_row(entry)
		frappe.set_user(JOINER)

		with (
			patch("frappe.get_roles", return_value=["Sales User"]),
			patch("klik_pos.api.pos_entry._get_open_pos_entry", return_value=row),
		):
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				create_closing_entry()

	def test_a_manager_can_close_someone_elses_stale_shift(self):
		entry = _shift(self.till, OPENER, days_ago=1)
		row = self._entry_row(entry)
		frappe.set_user(JOINER)

		with (
			patch("frappe.get_roles", return_value=["Sales Manager"]),
			patch("klik_pos.api.pos_entry._get_open_pos_entry", return_value=row),
			patch("klik_pos.api.pos_entry._calculate_payment_reconciliation", return_value=[]),
			patch("klik_pos.api.pos_entry._create_and_submit_closing_doc") as mock_create,
		):
			mock_create.return_value = frappe._dict(name="POS-CLO-FAKE")
			result = create_closing_entry()

		self.assertEqual(result["name"], "POS-CLO-FAKE")


class TestCurrentShiftStateManagerField(SharedShiftCase):
	def test_it_carries_manager(self):
		_shift(self.till, OPENER)
		frappe.set_user(OPENER)

		with patch("frappe.get_roles", return_value=["Sales Manager"]):
			self.assertTrue(current_shift_state()["manager"])
		with patch("frappe.get_roles", return_value=["Sales User"]):
			self.assertFalse(current_shift_state()["manager"])
