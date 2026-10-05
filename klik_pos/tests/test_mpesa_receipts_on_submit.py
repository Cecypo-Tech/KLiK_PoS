"""M-Pesa receipts ride the submit: no invoice, and no receipt number, until the sale is submitted.

The checkout used to make a draft Sales Invoice the moment receipts were picked, which drew
the next CS- number; an abandoned receipt checkout left a gap in the receipt book (CS-00620 on
FAC.Allparts). Now the pick only checks (check_mpesa_receipts) and the picks travel in the
submit payload as `mpesaReceipts`.

End to end against the site's open shift, like test_checkout_payment_scenarios: every
checkout commits, so cleanup cancels and deletes what each test made.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.mpesa import _mpesa_shortcodes_for_company, check_mpesa_receipts
from klik_pos.api.sales_invoice import (
	CHECKOUT_REQUEST_DOCTYPE,
	create_draft_invoice,
	process_queued_sales_invoice,
	queue_sales_invoice,
	submit_draft_invoice,
)
from klik_pos.tests.credit_fixtures import make_credit_note
from klik_pos.tests.mpesa_fixtures import make_c2b_payment
from klik_pos.tests.pos_fixtures import payable_total, pick_payment_mode, pos_profile_settings

ITEM_GROUP = "TEST-RCPT-GROUP"
ITEM_CODE = "TEST-RCPT-ITEM"
CUSTOMER = "TEST-RCPT-CUSTOMER"
OTHER_CUSTOMER = "TEST-RCPT-OTHER"
SERVICE_ITEM = "TEST-RCPT-SERVICE"  # what the vouchers' credit notes were for


def _ensure_customer(name):
	if not frappe.db.exists("Customer", name):
		customer = frappe.new_doc("Customer")
		customer.customer_name = name
		customer.customer_type = "Individual"
		customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		customer.insert(ignore_permissions=True)
	return name


def _mpesa_mode(profile_name):
	from klik_pos.api.mpesa import is_mpesa_mode

	modes = frappe.get_all(
		"POS Payment Method", filters={"parent": profile_name}, pluck="mode_of_payment", order_by="idx asc"
	)
	return next((m for m in modes if is_mpesa_mode(m)), None)


class TestReceiptsRideTheSubmit(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ready = False

		from klik_pos.api.sales_invoice import get_current_pos_opening_entry
		from klik_pos.klik_pos.utils import get_current_pos_profile

		if not get_current_pos_opening_entry():
			return
		try:
			cls.pos_profile = get_current_pos_profile()
		except Exception:
			return
		cls.company = cls.pos_profile.company
		cls.warehouse = cls.pos_profile.warehouse
		cls.cash_mode = pick_payment_mode(cls.pos_profile.name)
		cls.mode = _mpesa_mode(cls.pos_profile.name)
		shortcodes = _mpesa_shortcodes_for_company(cls.company)
		if not (cls.warehouse and cls.mode and cls.cash_mode and shortcodes):
			return
		cls.shortcode = shortcodes[0]
		_ensure_customer(CUSTOMER)
		_ensure_customer(OTHER_CUSTOMER)

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.update(
				{"item_code": ITEM_CODE, "item_name": ITEM_CODE, "item_group": ITEM_GROUP, "stock_uom": "Nos",
				 "is_stock_item": 1, "is_sales_item": 1}
			)
			item.insert(ignore_permissions=True)

		if not frappe.db.exists("Item", SERVICE_ITEM):
			item = frappe.new_doc("Item")
			item.update(
				{"item_code": SERVICE_ITEM, "item_name": SERVICE_ITEM, "item_group": ITEM_GROUP, "stock_uom": "Nos",
				 "is_stock_item": 0, "is_sales_item": 1}
			)
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
				_remove("Sales Invoice", name)
			_remove("Stock Entry", cls.stock_entry.name)
			for name in frappe.get_all("Bin", filters={"item_code": ITEM_CODE}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			for doctype, name in (("Item", ITEM_CODE), ("Item", SERVICE_ITEM), ("Item Group", ITEM_GROUP)):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no open POS shift with an M-Pesa mode and shortcode on this site")
		frappe.set_user("Administrator")

	# -- helpers ---------------------------------------------------------------------------

	def _items(self):
		return [{"id": ITEM_CODE, "item_code": ITEM_CODE, "quantity": 1, "price": 100, "uom": "Nos"}]

	def _total(self):
		return payable_total(CUSTOMER, self._items(), self.cash_mode)

	def _receipt(self, amount):
		row = make_c2b_payment(company=self.company, shortcode=self.shortcode, amount=amount, msisdn="254700000777")
		frappe.db.commit()
		self.addCleanup(self._remove_receipt, row.name)
		return row

	def _remove_receipt(self, name):
		pe = frappe.db.get_value("Mpesa C2B Payment Register", name, "payment_entry")
		frappe.db.set_value("Mpesa C2B Payment Register", name, "docstatus", 0, update_modified=False)
		frappe.delete_doc("Mpesa C2B Payment Register", name, force=True, ignore_permissions=True)
		if pe:
			_remove("Payment Entry", pe)
		frappe.db.commit()

	def _payload(self, receipts, customer=CUSTOMER, paid=0, background=False):
		request_id = frappe.generate_hash(length=24)
		self.addCleanup(_delete_request, request_id)
		return {
			"checkout_request_id": request_id,
			"customer": {"id": customer},
			"items": self._items(),
			"amountPaid": paid,
			"paymentMethods": [{"method": self.cash_mode, "amount": paid}] if paid else [],
			"businessType": "B2C",
			"enable_background_invoice_submission": background,
			"mpesaReceipts": {"mode_of_payment": self.mode, "payments": [r.name for r in receipts]},
		}

	def _sell(self, payload):
		with pos_profile_settings(self.pos_profile.name, allow_partial_payment=0):
			response = queue_sales_invoice(payload)
		if response.get("invoice_name"):
			self.addCleanup(_remove, "Sales Invoice", response["invoice_name"])
		frappe.db.commit()
		return response

	def _invoice_count(self):
		"""Invoices on the site: a refused checkout must leave none behind."""
		return frappe.db.sql("SELECT COUNT(*) FROM `tabSales Invoice`")[0][0]

	def _assert_paid_by(self, invoice_name, receipt, allocated):
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(flt(invoice.total_advance), flt(allocated))
		self.assertEqual([c.mpesa_c2b_payment_register for c in invoice.custom_mpesa_reconciled_payments], [receipt.name])
		self.assertEqual(frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "docstatus"), 1)
		return invoice

	# -- the pick ----------------------------------------------------------------------------

	def test_the_pick_checks_and_writes_nothing(self):
		receipt = self._receipt(500)
		invoices_before = self._invoice_count()

		result = check_mpesa_receipts(CUSTOMER, receipt.name)

		self.assertEqual(result["payments"], [{"name": receipt.name, "transid": receipt.transid, "amount": 500.0}])
		self.assertEqual(self._invoice_count(), invoices_before, "the pick made an invoice")
		self.assertEqual(frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "docstatus"), 0)

	def test_the_pick_refuses_a_receipt_picked_twice(self):
		receipt = self._receipt(500)
		with self.assertRaises(frappe.ValidationError):
			check_mpesa_receipts(CUSTOMER, f"{receipt.name},{receipt.name}")

	# -- the submit --------------------------------------------------------------------------

	def test_a_receipt_paid_sale_submits_directly_and_consumes_the_receipt(self):
		receipt = self._receipt(5000)
		response = self._sell(self._payload([receipt]))

		self.assertTrue(response["success"], response.get("message"))
		self._assert_paid_by(response["invoice_name"], receipt, self._total())
		leftover = sum(flt(r.get("excess_amount")) for r in response.get("mpesa_reconciliation") or [])
		self.assertEqual(leftover, flt(5000 - self._total()), "the leftover is reported for the cashier's toast")

	def test_a_receipt_paid_sale_goes_through_the_queue(self):
		receipt = self._receipt(5000)
		response = self._sell(self._payload([receipt], background=True))

		self.assertTrue(response["success"], response.get("message"))
		draft = frappe.get_doc("Sales Invoice", response["invoice_name"])
		self.assertEqual([c.mpesa_c2b_payment_register for c in draft.custom_mpesa_reconciled_payments], [receipt.name])

		process_queued_sales_invoice(draft.name, requested_by="Administrator")
		frappe.db.commit()
		self._assert_paid_by(draft.name, receipt, self._total())

	def test_cash_and_a_receipt_pay_together(self):
		receipt = self._receipt(5000)
		response = self._sell(self._payload([receipt], paid=50))

		self.assertTrue(response["success"], response.get("message"))
		self._assert_paid_by(response["invoice_name"], receipt, self._total() - 50)

	def test_a_spent_receipt_is_refused_and_no_invoice_number_is_used(self):
		receipt = self._receipt(5000)
		self.assertTrue(self._sell(self._payload([receipt]))["success"])
		frappe.db.set_value(
			"Payment Entry",
			frappe.db.get_value("Mpesa C2B Payment Register", receipt.name, "payment_entry"),
			"unallocated_amount",
			0,
		)
		frappe.db.commit()
		invoices_before = self._invoice_count()

		response = self._sell(self._payload([receipt]))

		self.assertFalse(response["success"])
		self.assertIn("nothing left", response["message"])
		self.assertNotIn("invoice_name", response, "a refused pick must not leave a numbered draft")
		self.assertEqual(self._invoice_count(), invoices_before)

	def test_a_receipt_held_by_another_customer_is_refused_at_submit(self):
		"""Picked for one customer, then the sale was switched to another."""
		receipt = self._receipt(5000)
		self.assertTrue(self._sell(self._payload([receipt]))["success"])

		response = self._sell(self._payload([receipt], customer=OTHER_CUSTOMER))

		self.assertFalse(response["success"])
		self.assertIn("held by", response["message"])
		self.assertNotIn("invoice_name", response)

	def test_a_resumed_draft_takes_its_receipts_at_submit(self):
		draft = create_draft_invoice(
			{"customer": {"id": CUSTOMER}, "items": self._items(), "paymentMethods": [], "amountPaid": 0,
			 "businessType": "B2C", "status": "held"}
		)
		name = draft.get("invoice_name") or draft["invoice"]["name"]
		self.addCleanup(_remove, "Sales Invoice", name)
		frappe.db.commit()
		receipt = self._receipt(5000)
		payload = self._payload([receipt])
		payload.pop("checkout_request_id")

		with pos_profile_settings(self.pos_profile.name, allow_partial_payment=0):
			response = submit_draft_invoice(name, payload)
		frappe.db.commit()

		self.assertTrue(response["success"], response.get("error"))
		self._assert_paid_by(name, receipt, self._total())

	# -- with vouchers -----------------------------------------------------------------------

	def _voucher(self, amount):
		"""A credit note worth `amount` to the customer; removed after the sale that used it."""
		note = make_credit_note(CUSTOMER, self.company, amount, item=SERVICE_ITEM)
		original = note.return_against
		entry = frappe.db.get_value(
			"Payment Entry Reference", {"reference_name": original, "docstatus": 1}, "parent"
		)
		frappe.db.commit()
		self.addCleanup(_remove, "Sales Invoice", original)
		self.addCleanup(_remove, "Payment Entry", entry)
		self.addCleanup(_remove, "Sales Invoice", note.name)
		return note

	def _assert_voucher_and_receipt_paid(self, invoice_name, receipt, note):
		"""The receipt covers what the voucher leaves, and the voucher settled its part."""
		voucher = -flt(note.grand_total)
		invoice = self._assert_paid_by(invoice_name, receipt, self._total() - voucher)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", note.name, "outstanding_amount")), 0)
		return invoice

	def test_a_voucher_and_a_receipt_pay_together(self):
		note = self._voucher(30)
		receipt = self._receipt(5000)
		payload = self._payload([receipt])
		payload["customerCredit"] = [{"invoice": note.name, "amount": 30}]

		response = self._sell(payload)

		self.assertTrue(response["success"], response.get("message"))
		self.assertEqual(flt(response["customer_credit"]["applied"], 2), 30)
		self.assertIsNone(response["customer_credit"]["warning"])
		self._assert_voucher_and_receipt_paid(response["invoice_name"], receipt, note)

	def test_a_voucher_and_a_receipt_pay_a_queued_sale(self):
		note = self._voucher(30)
		receipt = self._receipt(5000)
		rows = [{"invoice": note.name, "amount": 30}]
		payload = self._payload([receipt], background=True)
		payload["customerCredit"] = rows

		response = self._sell(payload)
		self.assertTrue(response["success"], response.get("message"))
		with pos_profile_settings(self.pos_profile.name, allow_partial_payment=0):
			result = process_queued_sales_invoice(
				response["invoice_name"], requested_by="Administrator", customer_credit=rows
			)
		frappe.db.commit()

		self.assertTrue(result.get("success"), result)
		self._assert_voucher_and_receipt_paid(response["invoice_name"], receipt, note)


def _remove(doctype, name):
	if not name or not frappe.db.exists(doctype, name):
		return
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.cancel()
	frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _delete_request(request_id):
	if frappe.db.exists(CHECKOUT_REQUEST_DOCTYPE, request_id):
		frappe.delete_doc(CHECKOUT_REQUEST_DOCTYPE, request_id, force=True, ignore_permissions=True)
		frappe.db.commit()
