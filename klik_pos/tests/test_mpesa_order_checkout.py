"""An STK-push sale is held as a draft Sales Order until the cashier submits it.

The payment dialog used to make a draft Sales Invoice before every push, and kept it for good
once a push went out, so every unpaid attempt left a POS-numbered invoice draft behind
(POS-01587, POS-01588 on dev). The push now names a draft Sales Order instead; submitting turns
it into the invoice the way a held order checks out - the invoice records the order, the push
is pointed at the invoice, and the order is deleted.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import mpesa_order, sales_order
from klik_pos.api.mpesa_order import discard_mpesa_order, save_mpesa_order, submit_mpesa_order
from klik_pos.api.sales_order import (
	delete_held_order,
	delete_held_orders_for_opening_entry,
	get_held_order_details,
	get_held_orders,
)
from klik_pos.tests.test_held_order_orphans import COMPANY, CUSTOMER, ITEM, PROFILE

EXPRESS = "Mpesa Express Request"


@contextmanager
def _at_till():
	"""Administrator standing at the test till, with no shift open."""
	profile = frappe.get_doc("POS Profile", PROFILE)
	with (
		patch.object(sales_order, "_get_active_pos_profile", return_value=profile),
		patch.object(sales_order, "get_current_pos_opening_entry", return_value=""),
	):
		yield


def _cart(price=10):
	return {
		"customer": {"id": CUSTOMER},
		"items": [{"id": ITEM, "item_code": ITEM, "quantity": 1, "price": price, "uom": "Nos"}],
		"paymentMethods": [],
		"businessType": "B2C",
		"status": "held",
	}


def _order():
	with _at_till():
		result = save_mpesa_order(_cart())
	assert result["success"], result
	return result["order_name"]


def _push(order_name, status, reference=None):
	"""An Mpesa Express Request sent from the order (submitted, as the real ones are)."""
	doctype, name = reference or ("Sales Order", order_name)
	doc = frappe.get_doc(
		{
			"doctype": EXPRESS,
			"name": f"_Test MEXP {frappe.generate_hash(length=8)}",
			"docstatus": 1,
			"status": status,
			"reference_doctype": doctype,
			"reference_name": name,
			"account_reference": order_name,
			"phone_number": "254700000123",
			"currency": "KES",
			"base_amount": 10,
			"amount": 10,
		}
	)
	doc.db_insert()
	return doc.name


def _draft_invoice(*_args, **_kwargs):
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = CUSTOMER
	invoice.company = COMPANY
	invoice.append("items", {"item_code": ITEM, "qty": 1, "rate": 10})
	invoice.insert(ignore_permissions=True)
	return invoice.name


def _exists(order_name):
	return bool(frappe.db.exists("Sales Order", order_name))


class TestSavingTheMpesaOrder(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_the_push_gets_a_draft_order_not_an_invoice(self):
		invoices_before = frappe.db.count("Sales Invoice")

		name = _order()

		order = frappe.get_doc("Sales Order", name)
		self.assertEqual(order.docstatus, 0)
		self.assertEqual(order.custom_klik_mpesa_order, 1)
		self.assertEqual(order.custom_is_klik_held, 0, "an order in checkout is not a hold")
		self.assertEqual(frappe.db.count("Sales Invoice"), invoices_before)

	def test_sending_again_updates_the_same_order_to_the_cart(self):
		name = _order()

		with _at_till():
			result = save_mpesa_order({**_cart(price=4), "mpesa_order_id": name})

		self.assertEqual(result["order_name"], name)
		self.assertEqual(frappe.db.get_value("Sales Order Item", {"parent": name}, "rate"), 4)

	def test_a_kept_order_resumed_for_another_push_leaves_the_held_tab(self):
		name = _order()
		frappe.db.set_value("Sales Order", name, "custom_is_klik_held", 1)

		with _at_till():
			save_mpesa_order({**_cart(), "mpesa_order_id": name})

		self.assertEqual(frappe.db.get_value("Sales Order", name, "custom_is_klik_held"), 0)

	def test_an_ordinary_held_order_is_not_taken_over(self):
		name = _order()
		frappe.db.set_value("Sales Order", name, {"custom_klik_mpesa_order": 0, "custom_is_klik_held": 1})

		with _at_till():
			result = save_mpesa_order({**_cart(), "mpesa_order_id": name})

		self.assertFalse(result["success"])


class TestSubmittingTheMpesaOrder(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.order = _order()

	def _submit(self, **kwargs):
		with _at_till(), patch.object(mpesa_order, "_create_invoice_draft", side_effect=_draft_invoice):
			return submit_mpesa_order(self.order, **kwargs)

	def test_submit_turns_the_order_into_the_invoice(self):
		push = _push(self.order, "Completed")

		result = self._submit()

		self.assertTrue(result["success"], result)
		invoice = result["invoice_name"]
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "docstatus"), 1)
		self.assertFalse(_exists(self.order), "the order outlived its sale")
		self.assertEqual(
			frappe.db.get_value(EXPRESS, push, ["reference_doctype", "reference_name"]),
			("Sales Invoice", invoice),
		)
		if frappe.get_meta("Sales Invoice").has_field("powerpack_source_order"):
			self.assertEqual(
				frappe.db.get_value("Sales Invoice", invoice, "powerpack_source_order"), self.order
			)

	def test_failed_pushes_follow_the_order_to_the_invoice(self):
		failed = _push(self.order, "Failed")
		_push(self.order, "Completed")

		result = self._submit()

		self.assertTrue(result["success"], result)
		self.assertEqual(frappe.db.get_value(EXPRESS, failed, "reference_name"), result["invoice_name"])

	def test_refused_while_a_push_still_waits_on_the_customer(self):
		_push(self.order, "In Progress")
		invoices_before = frappe.db.count("Sales Invoice")

		result = self._submit()

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "mpesa_request_waiting")
		self.assertTrue(_exists(self.order))
		self.assertEqual(frappe.db.count("Sales Invoice"), invoices_before)

	def test_a_refused_submit_leaves_no_invoice_draft_and_keeps_the_order(self):
		push = _push(self.order, "Completed")
		invoices_before = frappe.db.count("Sales Invoice")

		with patch.object(
			mpesa_order,
			"submit_draft_invoice",
			return_value={"success": False, "error": "M-Pesa row not backed"},
		):
			result = self._submit()

		self.assertFalse(result["success"])
		self.assertEqual(frappe.db.count("Sales Invoice"), invoices_before, "a refused submit left a draft")
		self.assertTrue(_exists(self.order))
		self.assertEqual(frappe.db.get_value(EXPRESS, push, "reference_doctype"), "Sales Order")

	def test_submitting_again_after_success_answers_with_the_invoice(self):
		"""A network drop after the server finished: the retry must not ring the sale up twice."""
		_push(self.order, "Completed")
		first = self._submit()
		invoices_after_first = frappe.db.count("Sales Invoice")

		again = self._submit()

		self.assertTrue(again["success"], again)
		self.assertEqual(again["invoice_name"], first["invoice_name"])
		self.assertEqual(frappe.db.count("Sales Invoice"), invoices_after_first)

	def test_an_order_gone_without_an_invoice_is_reported(self):
		frappe.delete_doc("Sales Order", self.order, force=True, ignore_permissions=True)

		result = self._submit()

		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "held_order_gone")


class TestLeavingCheckout(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.order = _order()

	def _discard(self):
		with _at_till():
			return discard_mpesa_order(self.order)

	def test_an_order_whose_pushes_all_failed_is_deleted(self):
		_push(self.order, "Failed")

		result = self._discard()

		self.assertTrue(result["success"], result)
		self.assertFalse(result.get("kept"))
		self.assertFalse(_exists(self.order))

	def test_an_order_with_no_push_is_deleted(self):
		self.assertTrue(self._discard()["success"])
		self.assertFalse(_exists(self.order))

	def test_an_order_with_a_live_push_is_kept_as_a_held_order(self):
		for status in ("In Progress", "Completed"):
			with self.subTest(status=status):
				frappe.db.delete(EXPRESS, {"account_reference": self.order})
				frappe.db.set_value("Sales Order", self.order, "custom_is_klik_held", 0)
				_push(self.order, status)

				result = self._discard()

				self.assertTrue(result["kept"], result)
				self.assertIn("Held", result["message"])
				self.assertTrue(_exists(self.order))
				self.assertEqual(frappe.db.get_value("Sales Order", self.order, "custom_is_klik_held"), 1)

	def test_only_an_mpesa_order_is_discarded(self):
		frappe.db.set_value(
			"Sales Order", self.order, {"custom_klik_mpesa_order": 0, "custom_is_klik_held": 1}
		)

		result = self._discard()

		self.assertFalse(result["success"])
		self.assertTrue(_exists(self.order))


class TestKeptOrdersAreNotLost(FrappeTestCase):
	"""A kept M-Pesa order sits on the Held tab; nothing may delete it while its push is live."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.order = _order()
		frappe.db.set_value(
			"Sales Order", self.order, {"custom_is_klik_held": 1, "custom_pos_opening_entry": "POS-OPE-MPESA"}
		)

	def test_the_cashier_cannot_delete_it_while_its_push_is_live(self):
		_push(self.order, "Completed")

		with _at_till():
			result = delete_held_order(self.order)

		self.assertFalse(result["success"])
		self.assertIn("M-Pesa", result["error"])
		self.assertTrue(_exists(self.order))

	def test_the_cashier_can_delete_it_once_its_pushes_failed(self):
		_push(self.order, "Failed")

		with _at_till():
			result = delete_held_order(self.order)

		self.assertTrue(result["success"], result)
		self.assertFalse(_exists(self.order))

	def test_a_shift_close_skips_it_while_its_push_is_live(self):
		_push(self.order, "In Progress")

		delete_held_orders_for_opening_entry("POS-OPE-MPESA")

		self.assertTrue(_exists(self.order))

	def test_a_shift_close_clears_it_once_its_pushes_failed(self):
		_push(self.order, "Failed")

		delete_held_orders_for_opening_entry("POS-OPE-MPESA")

		self.assertFalse(_exists(self.order))


class TestResumingAKeptOrder(FrappeTestCase):
	"""Resumed from the Held tab, checkout must see the push already sent, not charge again."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.order = _order()
		frappe.db.set_value("Sales Order", self.order, "custom_is_klik_held", 1)

	def test_the_details_carry_the_last_push(self):
		_push(self.order, "Failed")
		paid = _push(self.order, "Completed")
		frappe.db.set_value(EXPRESS, paid, {"transaction_id": "UJ1TEST001", "payment_gateway": "Mpesa-Test"})

		with _at_till():
			details = get_held_order_details(self.order)

		self.assertTrue(details["mpesa_order"])
		self.assertEqual(details["mpesa_request"]["name"], paid)
		self.assertEqual(details["mpesa_request"]["status"], "Completed")
		self.assertEqual(details["mpesa_request"]["transaction_id"], "UJ1TEST001")
		self.assertEqual(details["mpesa_request"]["payment_gateway"], "Mpesa-Test")

	def test_an_ordinary_held_order_has_no_push(self):
		frappe.db.set_value("Sales Order", self.order, "custom_klik_mpesa_order", 0)

		with _at_till():
			details = get_held_order_details(self.order)

		self.assertFalse(details["mpesa_order"])
		self.assertIsNone(details["mpesa_request"])

	def test_the_held_tab_marks_it_as_an_mpesa_order(self):
		with _at_till():
			listed = get_held_orders(limit=200, skip_opening_entry_filter=True)

		row = next((o for o in listed["data"] if o["name"] == self.order), None)
		self.assertIsNotNone(row, "kept order not on the Held tab")
		self.assertTrue(row["mpesa_order"])
