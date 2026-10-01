"""A held order paid by M-Pesa is finished through its M-Pesa draft, not checkout_held_order.

M-Pesa needs an invoice number before the money moves, so the payment dialog makes a draft
Sales Invoice and later submits it with submit_draft_invoice. That path knew nothing of the
held order the cart came from: the order was never locked, access-checked, linked or deleted,
so it stayed on the Held tab after the sale and could be checked out a second time.
submit_draft_invoice now takes the order's id and finishes it the way checkout does.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_invoice
from klik_pos.api.sales_invoice import submit_draft_invoice
from klik_pos.tests.test_held_order_access_rule import SOMEONE_ELSE, _as_cashier, _order, _till
from klik_pos.tests.test_held_order_orphans import COMPANY, CUSTOMER, ITEM


def _draft():
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = CUSTOMER
	invoice.company = COMPANY
	invoice.append("items", {"item_code": ITEM, "qty": 1, "rate": 10})
	invoice.insert(ignore_permissions=True)
	return invoice


def _docstatus(invoice):
	return frappe.db.get_value("Sales Invoice", invoice.name, "docstatus")


def _held(so):
	return bool(frappe.db.exists("Sales Order", so.name))


class TestMpesaDraftFinishesTheHeldOrder(FrappeTestCase):
	def test_submitting_the_draft_finishes_the_held_order(self):
		so, draft = _order(opening_entry=""), _draft()

		with _as_cashier(_till(1)):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		self.assertTrue(result["success"], result)
		self.assertEqual(_docstatus(draft), 1)
		self.assertFalse(_held(so), "the held order outlived its sale")
		if frappe.get_meta("Sales Invoice").has_field("powerpack_source_order"):
			self.assertEqual(frappe.db.get_value("Sales Invoice", draft.name, "powerpack_source_order"), so.name)

	def test_a_gone_order_is_refused_and_the_draft_left_alone(self):
		so, draft = _order(opening_entry=""), _draft()
		frappe.delete_doc("Sales Order", so.name, force=1, ignore_permissions=True)

		with _as_cashier(_till(1)):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "held_order_gone")
		self.assertEqual(result["order_id"], so.name)
		self.assertEqual(_docstatus(draft), 0)

	def test_another_cashier_s_order_is_refused_on_a_till_that_keeps_them_apart(self):
		so, draft = _order(opening_entry="", owner=SOMEONE_ELSE), _draft()

		with _as_cashier(_till(0)):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		self.assertFalse(result["success"])
		self.assertEqual(_docstatus(draft), 0)
		self.assertTrue(_held(so))

	def test_a_failed_submit_keeps_the_held_order(self):
		so, draft = _order(opening_entry=""), _draft()

		with (
			_as_cashier(_till(1)),
			patch.object(sales_invoice, "_enforce_submit_permission", side_effect=frappe.ValidationError("no")),
		):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		self.assertFalse(result["success"])
		self.assertEqual(_docstatus(draft), 0)
		self.assertTrue(_held(so))

	def test_a_price_breach_needing_approval_is_refused_as_at_checkout(self):
		so, draft = _order(opening_entry=""), _draft()

		with (
			_as_cashier(_till(1)),
			patch.object(
				sales_invoice, "_refuse_unapproved_price_breach", side_effect=frappe.ValidationError("approve")
			) as refuse,
		):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		refuse.assert_called_once()
		self.assertFalse(result["success"])
		self.assertTrue(_held(so))

	def test_a_queued_submit_also_finishes_the_held_order(self):
		so, draft = _order(opening_entry=""), _draft()
		frappe.db.set_value("Sales Invoice", draft.name, "enable_background_invoice_submission", 1)

		with (
			_as_cashier(_till(1)),
			patch.object(sales_invoice, "_needs_shift_check", return_value=False),
			patch.object(sales_invoice, "_reserve_stock_for_queued_invoice"),
			patch.object(sales_invoice.frappe, "enqueue"),
		):
			result = submit_draft_invoice(draft.name, held_order_id=so.name)

		self.assertTrue(result["success"], result)
		self.assertFalse(_held(so))

	def test_a_draft_with_no_held_order_leaves_held_orders_alone(self):
		so, draft = _order(opening_entry=""), _draft()

		with _as_cashier(_till(1)):
			result = submit_draft_invoice(draft.name)

		self.assertTrue(result["success"], result)
		self.assertEqual(_docstatus(draft), 1)
		self.assertTrue(_held(so))


class TestMpesaDraftIsNotAHold(FrappeTestCase):
	"""create_draft_invoice's only caller is M-Pesa: its draft is a payment in progress."""

	def test_the_draft_is_not_flagged_held(self):
		if not frappe.get_meta("Sales Invoice").has_field("custom_is_held"):
			self.skipTest("no custom_is_held on this site")
		unsaved = frappe.new_doc("Sales Invoice")
		unsaved.customer, unsaved.company = CUSTOMER, COMPANY
		unsaved.append("items", {"item_code": ITEM, "qty": 1, "rate": 10})
		parsed = (CUSTOMER, [], 0, [], None, "B2C", 0, 0, None, False, False, None, None, None, False, None)

		with (
			patch.object(sales_invoice, "parse_invoice_data", return_value=parsed),
			patch.object(sales_invoice, "build_sales_invoice_doc", return_value=unsaved),
			patch.object(sales_invoice, "validate_required_salesperson"),
		):
			result = sales_invoice.create_draft_invoice({"status": "held"})

		self.assertTrue(result["success"], result)
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["invoice_name"], "custom_is_held"), 0)


def _stk_request(invoice, status):
	if not frappe.db.exists("DocType", "Mpesa Express Request"):
		raise frappe.DoesNotExistError("frappe_mpsa_payments not installed")
	request = frappe.get_doc(
		{
			"doctype": "Mpesa Express Request",
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"status": status,
		}
	)
	request.db_insert()
	return request


def _klik_draft(**values):
	draft = _draft()
	frappe.db.set_value("Sales Invoice", draft.name, {"custom_is_created_from_klik": 1, **values})
	return draft


def _exists(invoice):
	return bool(frappe.db.exists("Sales Invoice", invoice.name))


class TestAnAbandonedMpesaDraftIsDiscarded(FrappeTestCase):
	"""Closing the dialog, or holding the order, used to leave the M-Pesa draft behind beside
	the held order. It goes - unless an STK push was sent from it: a payment still on its way
	(or already made) must find its invoice."""

	def test_the_cashier_s_own_draft_with_no_stk_push_is_discarded(self):
		draft = _klik_draft()
		result = sales_invoice.discard_mpesa_draft(draft.name)
		self.assertTrue(result["success"], result)
		self.assertFalse(_exists(draft))

	def test_a_draft_with_an_stk_push_in_progress_is_kept(self):
		draft = _klik_draft()
		_stk_request(draft, "In Progress")
		result = sales_invoice.discard_mpesa_draft(draft.name)
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "mpesa_request_sent")
		self.assertTrue(_exists(draft))

	def test_a_draft_already_paid_by_stk_is_kept(self):
		draft = _klik_draft()
		_stk_request(draft, "Completed")
		self.assertEqual(sales_invoice.discard_mpesa_draft(draft.name)["code"], "mpesa_request_sent")
		self.assertTrue(_exists(draft))

	def test_a_draft_whose_stk_push_failed_is_discarded(self):
		draft = _klik_draft()
		_stk_request(draft, "Failed")
		self.assertTrue(sales_invoice.discard_mpesa_draft(draft.name)["success"])
		self.assertFalse(_exists(draft))

	def test_someone_else_s_draft_is_kept(self):
		draft = _klik_draft(owner=SOMEONE_ELSE)
		self.assertFalse(sales_invoice.discard_mpesa_draft(draft.name)["success"])
		self.assertTrue(_exists(draft))

	def test_a_sale_waiting_for_the_background_worker_is_kept(self):
		draft = _klik_draft(enable_background_invoice_submission=1)
		self.assertFalse(sales_invoice.discard_mpesa_draft(draft.name)["success"])
		self.assertTrue(_exists(draft))

	def test_a_draft_not_made_by_the_pos_is_kept(self):
		draft = _draft()
		self.assertFalse(sales_invoice.discard_mpesa_draft(draft.name)["success"])
		self.assertTrue(_exists(draft))

	def test_deleting_a_draft_from_the_pos_also_keeps_one_with_a_live_stk_push(self):
		draft = _klik_draft()
		_stk_request(draft, "In Progress")
		result = sales_invoice.delete_draft_invoice(draft.name)
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "mpesa_request_sent")
		self.assertTrue(_exists(draft))
