"""A held order the POS is finishing may be gone: checked out by someone else, cleared by a
shift close, or submitted from the desk.

Both checkout and re-holding answered with prose only, so the POS kept retrying the same
order id and every attempt failed ("Cannot update held order SAL-ORD-2026-00033: it is no
longer a draft"). They now say so in a form the POS can act on, and only after a replay of
this very checkout has been ruled out - that one still returns the invoice it created.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.sales_order import checkout_held_order, create_held_order
from klik_pos.tests.test_held_order_access_rule import _as_cashier, _order, _payload, _till


class TestCheckoutOfAGoneOrder(FrappeTestCase):
	def test_a_deleted_order_is_reported_gone(self):
		so = _order(opening_entry="")
		name = so.name
		frappe.delete_doc("Sales Order", name, force=1, ignore_permissions=True)

		with _as_cashier(_till(1)):
			result = checkout_held_order(name, {"checkout_request_id": None})

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "held_order_gone")
		self.assertEqual(result["order_id"], name)

	def test_an_order_submitted_elsewhere_is_reported_gone(self):
		so = _order(opening_entry="")
		frappe.db.set_value("Sales Order", so.name, "docstatus", 1, update_modified=False)

		with _as_cashier(_till(1)):
			result = checkout_held_order(so.name, {"checkout_request_id": None})

		self.assertEqual(result["code"], "held_order_gone")

	def test_an_order_deleted_while_waiting_for_the_lock_is_reported_gone(self):
		so = _order(opening_entry="")
		with (
			_as_cashier(_till(1)),
			patch.object(
				sales_order, "_lock_held_order", side_effect=frappe.DoesNotExistError("already checked out")
			),
		):
			result = checkout_held_order(so.name, {"checkout_request_id": None})

		self.assertEqual(result["code"], "held_order_gone")

	def test_a_replay_of_this_checkout_still_returns_its_invoice(self):
		replay = {"success": True, "invoice_name": "POS-REPLAY"}
		with (
			_as_cashier(_till(1)),
			patch("klik_pos.api.sales_invoice._get_checkout_request", return_value=frappe._dict(name="abc")),
			patch("klik_pos.api.sales_invoice._checkout_request_response", return_value=replay),
		):
			result = checkout_held_order("SAL-ORD-GONE", {"checkout_request_id": "abc"})

		self.assertEqual(result, replay)


class TestReHoldingAGoneOrder(FrappeTestCase):
	def test_re_holding_a_deleted_order_is_reported_gone(self):
		so = _order(opening_entry="")
		name = so.name
		frappe.delete_doc("Sales Order", name, force=1, ignore_permissions=True)

		with _as_cashier(_till(1)):
			result = create_held_order(_payload(name))

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "held_order_gone")

	def test_re_holding_an_order_submitted_elsewhere_is_reported_gone(self):
		so = _order(opening_entry="")
		frappe.db.set_value("Sales Order", so.name, "docstatus", 1, update_modified=False)

		with _as_cashier(_till(1)):
			result = create_held_order(_payload(so.name))

		self.assertEqual(result["code"], "held_order_gone")
