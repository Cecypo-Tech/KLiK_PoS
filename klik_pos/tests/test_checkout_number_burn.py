"""A failed checkout must not burn a receipt number.

Production, 1-3 Sep 2026: the POS cash series CS-26- issued 266 numbers and kept 228
invoices. 38 receipts vanished, one for every Klik Checkout Request that ended Failed.

doc.insert() names the document before it validates -- frappe/model/document.py runs
set_new_name() at line 481, validate() at 486 and db_insert() at 497 -- so an ERPNext
validation throw leaves the Document Naming Rule counter incremented and no invoice row.
The trigger in production was a selling rate under valuation. queue_sales_invoice caught
that exception, recorded the failure and returned normally; nothing propagated, Frappe's
request handler committed, and the increment outlived the invoice that never existed.

These tests pin the property the client actually cares about -- consecutive successful
checkouts produce consecutive receipt numbers, no matter how many checkouts fail in
between -- and the two things a well-meaning refactor breaks: that _abort_checkout is the
only way out of the except block, and that the failure record is written after the
rollback instead of being eaten by it.

The failure is injected by making Sales Invoice.validate() throw. That is the same code
path as the production selling-price validation (both throw from validate(), after naming
and before the insert) without depending on Selling Settings or item valuation on the site
running the tests.
"""

import ast
import inspect
import textwrap
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice as checkout_module
from klik_pos.api.sales_invoice import (
	CHECKOUT_REQUEST_DOCTYPE,
	_abort_checkout,
	_CheckoutState,
	_claim_checkout_request,
	_record_failed_checkout_request,
	queue_sales_invoice,
)
from klik_pos.tests.pos_fixtures import (
	default_sales_tax_template,
	payable_total,
	pick_payment_mode,
	pos_profile_settings,
)

ITEM_GROUP = "TEST-BURN-GROUP"
ITEM_CODE = "TEST-BURN-ITEM"
FORCED_FAILURE = "Forced failure exercising the checkout abort path"
NAMING_RULE_PREFIX = "TESTBURN-"
CUSTOMER = "TEST-BURN-CUSTOMER"


def _delete_requests(*request_ids):
	for request_id in request_ids:
		if request_id and frappe.db.exists(CHECKOUT_REQUEST_DOCTYPE, request_id):
			frappe.delete_doc(CHECKOUT_REQUEST_DOCTYPE, request_id, force=True, ignore_permissions=True)


def _ensure_customer():
	"""A customer of our own, so the suite does not depend on incidental site data.

	Scavenging one off an existing Sales Invoice makes the tests silently skip on a fresh
	site or a staging clone - exactly where this fix most needs verifying.
	"""
	if frappe.db.exists("Customer", CUSTOMER):
		return CUSTOMER
	customer = frappe.new_doc("Customer")
	customer.customer_name = CUSTOMER
	customer.customer_type = "Individual"
	customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	customer.insert(ignore_permissions=True)
	return customer.name


def _trailing_number(name):
	"""'CS-26-00042' -> 42. The receipt number the cashier reads off the slip."""
	digits = ""
	for char in reversed(name):
		if not char.isdigit():
			break
		digits = char + digits
	if not digits:
		raise ValueError(f"{name} has no numeric tail")
	return int(digits)


@contextmanager
def _validation_always_fails():
	"""Throw from Sales Invoice.validate(), which runs after the name has been assigned."""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

	original = SalesInvoice.validate

	def failing(self):
		frappe.throw(FORCED_FAILURE)

	SalesInvoice.validate = failing
	try:
		yield
	finally:
		SalesInvoice.validate = original


@contextmanager
def _todo_validation_always_fails():
	"""The same injection for ToDo, used by the site-independent counter tests."""
	from frappe.desk.doctype.todo.todo import ToDo

	original = ToDo.validate

	def failing(self):
		frappe.throw(FORCED_FAILURE)

	ToDo.validate = failing
	try:
		yield
	finally:
		ToDo.validate = original


class TestNamingCounterIsRestored(FrappeTestCase):
	"""The invariant itself, against Frappe's real naming machinery.

	Runs on any site: no POS Profile, no open shift, no ERPNext fixtures. A Document Naming
	Rule on ToDo stands in for the POS receipt series and a ToDo whose validation throws
	stands in for the invoice that never landed. _abort_checkout is the real one, so this is
	a direct test of the guarantee the POS depends on rather than a simulation of it.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		rule = frappe.new_doc("Document Naming Rule")
		rule.document_type = "ToDo"
		rule.prefix = NAMING_RULE_PREFIX
		rule.prefix_digits = 5
		rule.counter = 0
		rule.insert(ignore_permissions=True)
		cls.rule_name = rule.name
		# Committed so the rollback under test cannot sweep the fixture away with it.
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for name in frappe.get_all(
			"ToDo", filters={"name": ["like", NAMING_RULE_PREFIX + "%"]}, pluck="name"
		):
			frappe.delete_doc("ToDo", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Document Naming Rule", cls.rule_name):
			frappe.delete_doc(
				"Document Naming Rule", cls.rule_name, force=True, ignore_permissions=True
			)
		frappe.db.commit()
		super().tearDownClass()

	def _counter(self):
		return frappe.db.get_value("Document Naming Rule", self.rule_name, "counter")

	def _create(self):
		todo = frappe.new_doc("ToDo")
		todo.description = "receipt number continuity probe"
		todo.insert(ignore_permissions=True)
		frappe.db.commit()
		return _trailing_number(todo.name)

	def _abort_a_failed_create(self):
		"""Consume a number, throw during validate, then abort the way a checkout does."""
		state = _CheckoutState()
		try:
			with _todo_validation_always_fails():
				todo = frappe.new_doc("ToDo")
				todo.description = "receipt number continuity probe"
				todo.insert(ignore_permissions=True)
		except Exception as error:
			return _abort_checkout(state, error)
		self.fail("the injected validation failure did not fail")

	def test_the_counter_is_restored_after_a_failed_create(self):
		before = self._counter()
		self._abort_a_failed_create()
		self.assertEqual(self._counter(), before, "the failed document burned a number")

	def test_numbers_stay_contiguous_across_a_burst_of_failures(self):
		# The production shape: one blocked cart retried over and over.
		first = self._create()
		for _ in range(25):
			self._abort_a_failed_create()
		second = self._create()
		self.assertEqual(
			second, first + 1, f"25 failed attempts burned {second - first - 1} numbers"
		)

	def test_numbers_stay_contiguous_when_failures_are_interleaved(self):
		numbers = []
		for _ in range(5):
			self._abort_a_failed_create()
			self._abort_a_failed_create()
			numbers.append(self._create())
		self.assertEqual(
			numbers,
			[numbers[0] + offset for offset in range(5)],
			f"numbers jumped: {numbers}",
		)


class TestAbortCheckoutContract(FrappeTestCase):
	"""The call-site and ordering rules, read straight off the source.

	These are structural on purpose. The burn is invisible in a passing checkout and only
	shows up as a gap in a receipt book weeks later, so the shape of the code is worth
	asserting directly rather than trusting a reviewer to notice.
	"""

	def test_abort_checkout_is_the_only_exit_from_a_failed_checkout(self):
		source = textwrap.dedent(inspect.getsource(checkout_module.queue_sales_invoice))
		function = ast.parse(source).body[0]

		top_level_try = [node for node in function.body if isinstance(node, ast.Try)]
		self.assertEqual(len(top_level_try), 1, "queue_sales_invoice should have one top-level try")

		handlers = top_level_try[0].handlers
		self.assertEqual(len(handlers), 1, "one handler, one failure path")

		body = handlers[0].body
		self.assertEqual(
			len(body),
			1,
			"the checkout except block must do nothing but delegate to _abort_checkout; "
			"anything it writes before the rollback inside _abort_checkout is discarded by it",
		)
		statement = body[0]
		self.assertIsInstance(statement, ast.Return, "the handler must return _abort_checkout(...)")
		self.assertIsInstance(statement.value, ast.Call)
		self.assertEqual(
			statement.value.func.id,
			"_abort_checkout",
			"a bare `return {'success': False, ...}` here burns a receipt number on every "
			"failed checkout - see the naming-counter burn guard comment in api/sales_invoice.py",
		)

	def test_the_rollback_runs_before_the_record_and_the_log(self):
		source = textwrap.dedent(inspect.getsource(checkout_module._abort_checkout))
		function = ast.parse(source).body[0]

		calls = []
		for node in ast.walk(function):
			if not isinstance(node, ast.Call):
				continue
			if isinstance(node.func, ast.Attribute):
				calls.append((node.lineno, node.func.attr))
			elif isinstance(node.func, ast.Name):
				calls.append((node.lineno, node.func.id))
		ordered = [name for _, name in sorted(calls)]

		for expected in ("rollback", "_record_failed_checkout_request", "log_error"):
			self.assertIn(expected, ordered, f"_abort_checkout no longer calls {expected}")

		self.assertLess(
			ordered.index("rollback"),
			ordered.index("_record_failed_checkout_request"),
			"the failure record must be written after the rollback, or the rollback discards it "
			"and retries create duplicate invoices",
		)
		self.assertLess(
			ordered.index("rollback"),
			ordered.index("log_error"),
			"the Error Log row must be written after the rollback or it is discarded with it",
		)

	def test_held_orders_roll_back_before_logging_too(self):
		from klik_pos.api import sales_order

		source = textwrap.dedent(inspect.getsource(sales_order.create_held_order))
		function = ast.parse(source).body[0]

		handlers = [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)]
		self.assertTrue(handlers)

		names = []
		for node in ast.walk(handlers[-1]):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
				names.append((node.lineno, node.func.attr))
		ordered = [name for _, name in sorted(names)]

		self.assertIn(
			"rollback",
			ordered,
			"create_held_order swallows its exception, so without a rollback the Sales Order "
			"naming counter increment is committed and an order number is burned",
		)
		self.assertLess(ordered.index("rollback"), ordered.index("log_error"))


class TestFailedCheckoutLedger(FrappeTestCase):
	"""The failure record has to survive the rollback that removes the claim row."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.request_id = frappe.generate_hash(length=24)
		self.addCleanup(_delete_requests, self.request_id)

	def _state(self, invoice_name=None):
		state = _CheckoutState()
		state.mark_claimed(self.request_id)
		state.invoice_name = invoice_name
		return state

	def test_the_record_is_inserted_when_the_rollback_removed_the_claim_row(self):
		# The trap a naive fix falls into: a bare frappe.db.rollback() discards the row
		# _claim_checkout_request inserted, and _update_checkout_request early-returns when
		# the row is gone. Recording therefore has to insert. If it does not, a retry finds
		# no ledger row, claims a fresh key and bills the customer twice - trading a skipped
		# receipt number for a duplicate sale.
		self.assertFalse(frappe.db.exists(CHECKOUT_REQUEST_DOCTYPE, self.request_id))

		_record_failed_checkout_request(self._state(), frappe.ValidationError(FORCED_FAILURE))

		row = frappe.db.get_value(
			CHECKOUT_REQUEST_DOCTYPE, self.request_id, ["status", "sales_invoice"], as_dict=True
		)
		self.assertIsNotNone(row, "a failed checkout left no ledger row - retries will duplicate")
		self.assertEqual(row.status, "Failed")
		self.assertFalse(row.sales_invoice, "no invoice was created, so none may be named")

	def test_the_record_updates_an_existing_row_without_duplicating_it(self):
		_claim_checkout_request(self.request_id)

		_record_failed_checkout_request(self._state(), frappe.ValidationError(FORCED_FAILURE))

		self.assertEqual(frappe.db.count(CHECKOUT_REQUEST_DOCTYPE, {"name": self.request_id}), 1)
		self.assertEqual(
			frappe.db.get_value(CHECKOUT_REQUEST_DOCTYPE, self.request_id, "status"), "Failed"
		)

	def test_a_checkout_without_a_key_records_nothing(self):
		before = frappe.db.count(CHECKOUT_REQUEST_DOCTYPE)
		_record_failed_checkout_request(_CheckoutState(), frappe.ValidationError(FORCED_FAILURE))
		self.assertEqual(frappe.db.count(CHECKOUT_REQUEST_DOCTYPE), before)


class TestReceiptNumberContinuity(FrappeTestCase):
	"""End to end: failed checkouts must leave no hole in the receipt sequence.

	Every successful checkout is committed, because the behaviour under test is a rollback
	and an uncommitted fixture would be swept away by it - which is precisely what happened
	to the 38 invoices in production, only there it was the counter that survived instead.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ready = False

		from klik_pos.api.sales_invoice import get_current_pos_opening_entry

		if not get_current_pos_opening_entry():
			return

		from klik_pos.klik_pos.utils import get_current_pos_profile

		try:
			cls.pos_profile = get_current_pos_profile()
		except Exception:
			# An open shift pointing at a deleted profile is a broken fixture, not a
			# failing assertion. Skip rather than report a red test for it.
			return
		cls.company = cls.pos_profile.company
		cls.warehouse = cls.pos_profile.warehouse or frappe.db.get_value(
			"Warehouse", {"is_group": 0, "company": cls.company}, "name"
		)
		cls.payment_mode = pick_payment_mode(cls.pos_profile.name)
		if not (cls.warehouse and cls.payment_mode):
			return
		cls.customer = _ensure_customer()

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": ITEM_GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = ITEM_CODE
			item.item_name = ITEM_CODE
			item.item_group = ITEM_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 1
			item.is_sales_item = 1
			item.insert(ignore_permissions=True)

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		cls.stock_entry = make_stock_entry(
			item_code=ITEM_CODE, target=cls.warehouse, qty=500, basic_rate=10, company=cls.company
		)
		frappe.db.commit()
		cls.ready = True

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "ready", False):
			for name in frappe.get_all(
				"Sales Invoice Item", filters={"item_code": ITEM_CODE}, pluck="parent", distinct=True
			):
				if not frappe.db.exists("Sales Invoice", name):
					continue
				invoice = frappe.get_doc("Sales Invoice", name)
				if invoice.docstatus == 1:
					invoice.flags.ignore_permissions = True
					invoice.cancel()
				frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

			if getattr(cls, "stock_entry", None) and frappe.db.exists("Stock Entry", cls.stock_entry.name):
				entry = frappe.get_doc("Stock Entry", cls.stock_entry.name)
				if entry.docstatus == 1:
					entry.flags.ignore_permissions = True
					entry.cancel()
				frappe.delete_doc("Stock Entry", cls.stock_entry.name, force=True, ignore_permissions=True)

			for name in frappe.get_all("Bin", filters={"item_code": ITEM_CODE}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			if frappe.db.exists("Item", ITEM_CODE):
				frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
			if frappe.db.exists("Item Group", ITEM_GROUP):
				frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", CUSTOMER):
				frappe.delete_doc("Customer", CUSTOMER, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no open POS Opening Entry / payment mode / customer on this site")
		frappe.set_user("Administrator")

	def _payload(self, request_id):
		self.addCleanup(_delete_requests, request_id)
		items = [
			{
				"id": ITEM_CODE,
				"item_code": ITEM_CODE,
				"quantity": 1,
				"price": 100,
				"uom": "Nos",
			}
		]
		# Pay what the invoice actually demands, tax included. Paying the line price
		# makes every sale here partially paid, which only passes while the POS Profile
		# happens to allow partial payment.
		total = payable_total(self.customer, items, self.payment_mode)
		return {
			"checkout_request_id": request_id,
			"customer": {"id": self.customer},
			"items": items,
			"amountPaid": total,
			"paymentMethods": [{"method": self.payment_mode, "amount": total}],
			"businessType": "B2C",
		}

	def _sell(self):
		"""One successful checkout, committed so a later rollback cannot sweep it away."""
		response = queue_sales_invoice(self._payload(frappe.generate_hash(length=24)))
		self.assertTrue(response["success"], response.get("message"))
		self.addCleanup(self._remove_invoice, response["invoice_name"])
		frappe.db.commit()
		return _trailing_number(response["invoice_name"])

	def _fail(self):
		"""One checkout that throws during validate, i.e. after the name was assigned."""
		with _validation_always_fails():
			response = queue_sales_invoice(self._payload(frappe.generate_hash(length=24)))
		self.assertFalse(response["success"], "the injected validation failure did not fail")
		self.assertIsNone(response.get("invoice_name"), "a failed checkout named an invoice")
		return response

	def _remove_invoice(self, name):
		if not name or not frappe.db.exists("Sales Invoice", name):
			return
		invoice = frappe.get_doc("Sales Invoice", name)
		if invoice.docstatus == 1:
			invoice.flags.ignore_permissions = True
			invoice.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_a_failed_checkout_does_not_skip_a_receipt_number(self):
		before = self._sell()
		self._fail()
		after = self._sell()

		self.assertEqual(
			after,
			before + 1,
			f"the failed checkout burned receipt number {before + 1}",
		)

	def test_a_burst_of_failed_checkouts_does_not_skip_receipt_numbers(self):
		# The production pattern. On 3 Sep one cashier hit the same blocked cart eleven
		# times between 15:31 and 15:52; every retry took another receipt number with it,
		# which is why the gaps arrived in blocks of five, six and nine rather than singly.
		before = self._sell()

		for _ in range(15):
			self._fail()

		after = self._sell()
		self.assertEqual(
			after,
			before + 1,
			f"15 failed checkouts burned {after - before - 1} receipt numbers",
		)

	def test_successful_checkouts_stay_contiguous_when_failures_are_interleaved(self):
		numbers = []
		for _ in range(3):
			self._fail()
			self._fail()
			numbers.append(self._sell())

		self.assertEqual(
			numbers,
			[numbers[0], numbers[0] + 1, numbers[0] + 2],
			f"receipt numbers jumped: {numbers}",
		)

	def test_a_failed_checkout_stays_replayable_and_creates_no_duplicate(self):
		# The rollback must not take the idempotency guard down with it.
		request_id = frappe.generate_hash(length=24)
		payload = self._payload(request_id)

		with _validation_always_fails():
			failed = queue_sales_invoice(payload)
		self.assertFalse(failed["success"])

		row = frappe.db.get_value(
			CHECKOUT_REQUEST_DOCTYPE, request_id, ["status", "sales_invoice"], as_dict=True
		)
		self.assertIsNotNone(row, "the rollback took the ledger row with it")
		self.assertEqual(row.status, "Failed")
		self.assertFalse(row.sales_invoice)

		invoices_before = frappe.db.count("Sales Invoice")
		retry = queue_sales_invoice(payload)
		self.assertTrue(retry["success"], retry.get("message"))
		self.addCleanup(self._remove_invoice, retry["invoice_name"])
		frappe.db.commit()

		self.assertEqual(
			frappe.db.count("Sales Invoice"),
			invoices_before + 1,
			"replaying a failed key created more than one invoice",
		)


CASHIER = "pos-cashier-burn@example.com"
CASHIER_ROLE = "Express Sales"
R_ITEM_GROUP = "TEST-BURN-R-GROUP"
R_ITEM_CODE = "TEST-BURN-R-ITEM"
PRICE_FLOOR = 500.0


@contextmanager
def _price_floor_enforced():
	"""Turn on ERPNext's selling-price validation without writing to tabSingles.

	Writing the Single collides with ERPNext's own test-data setup, which saves Selling
	Settings and System Settings through the document layer during the run. Forcing the
	lookup leaves the validation itself completely real - same comparison against
	last_purchase_rate, same throw, same message the cashiers saw in production - while
	keeping the toggle out of the database.
	"""
	original = frappe.get_single_value

	def patched(doctype, fieldname, *args, **kwargs):
		if doctype == "Selling Settings" and fieldname == "validate_selling_price":
			return 1
		return original(doctype, fieldname, *args, **kwargs)

	frappe.get_single_value = patched
	try:
		yield
	finally:
		frappe.get_single_value = original


class TestRestrictedSalesUser(FrappeTestCase):
	"""The cashiers who hit this in production were not administrators.

	`Express Sales` is this site's limited till role: it can create and submit a Sales
	Invoice but cannot cancel or amend one, and it has no write on Item Price. The price
	floor is enforced the way production enforces it - Selling Settings
	"validate_selling_price" against the item's last purchase rate - which ERPNext applies
	to every role alike, with no manager bypass
	(erpnext/controllers/selling_controller.py:286). So this is the real production
	scenario: a restricted cashier, blocked by a price rule they cannot override, retrying.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ready = False
		cls.stock_entry = None

		from klik_pos.api.sales_invoice import get_current_pos_opening_entry

		if not get_current_pos_opening_entry():
			return
		from klik_pos.klik_pos.utils import get_current_pos_profile

		try:
			profile = get_current_pos_profile()
		except Exception:
			return

		cls.profile = profile
		cls.company = profile.company
		cls.warehouse = profile.warehouse or frappe.db.get_value(
			"Warehouse", {"is_group": 0, "company": cls.company}, "name"
		)
		cls.payment_mode = pick_payment_mode(profile.name)
		if not (cls.warehouse and cls.payment_mode):
			return
		# The cashier has an Express role, and erpnext_express refuses tax rows with no
		# template. A profile with no template gets exactly that from the company default
		# (ERPNext's set_pos_fields blanks the name, keeps the rows), so pin the template
		# the way a real profile would have it. Administrator never sees this check.
		template = profile.taxes_and_charges or default_sales_tax_template(profile.company)
		if template:
			pinned = pos_profile_settings(profile.name, taxes_and_charges=template)
			pinned.__enter__()
			cls.addClassCleanup(pinned.__exit__, None, None, None)
		cls.customer = _ensure_customer()

		if not frappe.db.exists("Item Group", R_ITEM_GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": R_ITEM_GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", R_ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = R_ITEM_CODE
			item.item_name = R_ITEM_CODE
			item.item_group = R_ITEM_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 1
			item.is_sales_item = 1
			item.insert(ignore_permissions=True)

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		cls.stock_entry = make_stock_entry(
			item_code=R_ITEM_CODE, target=cls.warehouse, qty=500, basic_rate=10, company=cls.company
		)

		# The cashier: one limited role, nothing else.
		if not frappe.db.exists("User", CASHIER):
			user = frappe.new_doc("User")
			user.email = CASHIER
			user.first_name = "Burn Test Cashier"
			user.send_welcome_email = 0
			user.append("roles", {"role": CASHIER_ROLE})
			user.insert(ignore_permissions=True)

		if not any(u.user == CASHIER for u in profile.applicable_for_users):
			profile.append("applicable_for_users", {"user": CASHIER})
			profile.save(ignore_permissions=True)

		if not frappe.get_all(
			"POS Opening Entry", filters={"user": CASHIER, "docstatus": 1, "status": "Open"}
		):
			entry = frappe.new_doc("POS Opening Entry")
			entry.period_start_date = frappe.utils.now()
			entry.posting_date = frappe.utils.nowdate()
			entry.company = cls.company
			entry.pos_profile = profile.name
			entry.user = CASHIER
			entry.append("balance_details", {"mode_of_payment": cls.payment_mode, "opening_amount": 0})
			entry.insert(ignore_permissions=True)
			entry.submit()
			cls.opening_entry = entry.name

		# The price floor the cashier cannot override.
		frappe.db.set_value("Item", R_ITEM_CODE, "last_purchase_rate", PRICE_FLOOR)
		frappe.clear_document_cache("Item", R_ITEM_CODE)
		frappe.db.commit()
		cls.ready = True

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		if getattr(cls, "ready", False):
			for name in frappe.get_all(
				"POS Opening Entry", filters={"user": CASHIER}, pluck="name"
			):
				frappe.db.sql("update `tabPOS Opening Entry` set docstatus = 2 where name = %s", (name,))
				frappe.clear_document_cache("POS Opening Entry", name)
				frappe.delete_doc(
					"POS Opening Entry", name, force=True, ignore_permissions=True, ignore_on_trash=True
				)
			for name in frappe.get_all(
				"Sales Invoice Item", filters={"item_code": R_ITEM_CODE}, pluck="parent", distinct=True
			):
				if not frappe.db.exists("Sales Invoice", name):
					continue
				invoice = frappe.get_doc("Sales Invoice", name)
				if invoice.docstatus == 1:
					invoice.flags.ignore_permissions = True
					invoice.cancel()
				frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
			if cls.stock_entry and frappe.db.exists("Stock Entry", cls.stock_entry.name):
				entry = frappe.get_doc("Stock Entry", cls.stock_entry.name)
				if entry.docstatus == 1:
					entry.flags.ignore_permissions = True
					entry.cancel()
				frappe.delete_doc("Stock Entry", entry.name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Bin", filters={"item_code": R_ITEM_CODE}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			for doctype, name in (("Item", R_ITEM_CODE), ("Item Group", R_ITEM_GROUP), ("User", CASHIER)):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", CUSTOMER):
				frappe.delete_doc("Customer", CUSTOMER, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no usable POS shift on this site")
		frappe.set_user(CASHIER)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_the_cashier_really_is_restricted(self):
		"""Guard the premise: if this role stops being limited the tests below prove nothing."""
		roles = frappe.get_roles(CASHIER)
		self.assertIn(CASHIER_ROLE, roles)
		self.assertNotIn("System Manager", roles)
		self.assertNotIn("Accounts Manager", roles)
		self.assertTrue(frappe.has_permission("Sales Invoice", "create", user=CASHIER))
		self.assertTrue(frappe.has_permission("Sales Invoice", "submit", user=CASHIER))
		self.assertFalse(
			frappe.has_permission("Sales Invoice", "cancel", user=CASHIER),
			"the till role should not be able to cancel a sale",
		)
		self.assertFalse(
			frappe.has_permission("Item Price", "write", user=CASHIER),
			"the till role should not be able to change prices",
		)

	def _payload(self, price):
		request_id = frappe.generate_hash(length=24)
		self.addCleanup(_delete_requests, request_id)
		# `price` is the LINE price - the price-floor rule under test applies to the item
		# rate, not to the amount tendered. Only the tendered amount is the payable total.
		items = [
			{
				"id": R_ITEM_CODE,
				"item_code": R_ITEM_CODE,
				"quantity": 1,
				"price": price,
				"uom": "Nos",
			}
		]
		total = payable_total(self.customer, items, self.payment_mode)
		return {
			"checkout_request_id": request_id,
			"customer": {"id": self.customer},
			"items": items,
			"amountPaid": total,
			"paymentMethods": [{"method": self.payment_mode, "amount": total}],
			"businessType": "B2C",
		}

	def _sell_at(self, price):
		with _price_floor_enforced():
			response = queue_sales_invoice(self._payload(price))
		self.assertTrue(response["success"], response.get("message"))
		frappe.db.commit()
		return _trailing_number(response["invoice_name"])

	def _blocked_at(self, price):
		with _price_floor_enforced():
			response = queue_sales_invoice(self._payload(price))
		self.assertFalse(
			response["success"], f"selling at {price} below the {PRICE_FLOOR} floor was not blocked"
		)
		return response

	def test_the_price_floor_actually_blocks_the_cashier(self):
		# Guard the other premise: the block must come from the price rule, not from a
		# permission error or a broken fixture.
		response = self._blocked_at(PRICE_FLOOR / 5)
		self.assertIn("lower than its", response["message"])
		self.assertIsNone(response.get("invoice_name"))

	def test_a_blocked_sale_does_not_burn_a_receipt_number(self):
		before = self._sell_at(PRICE_FLOOR * 2)
		self._blocked_at(PRICE_FLOOR / 5)
		after = self._sell_at(PRICE_FLOOR * 2)
		self.assertEqual(after, before + 1, "the blocked sale burned a receipt number")

	def test_a_cashier_retrying_a_blocked_cart_burns_nothing(self):
		# 3 Sep, 15:31-15:52: one cashier hit the same block eleven times in twenty minutes.
		before = self._sell_at(PRICE_FLOOR * 2)
		for _ in range(11):
			self._blocked_at(PRICE_FLOOR / 5)
		after = self._sell_at(PRICE_FLOOR * 2)
		self.assertEqual(
			after, before + 1, f"eleven retries burned {after - before - 1} receipt numbers"
		)

	def test_a_blocked_sale_leaves_a_replayable_ledger_row(self):
		payload = self._payload(PRICE_FLOOR / 5)
		with _price_floor_enforced():
			response = queue_sales_invoice(payload)
		self.assertFalse(response["success"])

		row = frappe.db.get_value(
			CHECKOUT_REQUEST_DOCTYPE,
			payload["checkout_request_id"],
			["status", "sales_invoice", "requested_by"],
			as_dict=True,
		)
		self.assertIsNotNone(row, "the rollback took the ledger row with it")
		self.assertEqual(row.status, "Failed")
		self.assertFalse(row.sales_invoice)
		self.assertEqual(row.requested_by, CASHIER)
