"""Remarks typed at checkout travel with the sale: held, recalled, invoiced.

Sales Invoice has a Remarks field (More Info); Sales Order had none, so a note typed for a
held order had nowhere to live. klik_pos adds `remarks` to Sales Order (only where the site
has none), keeps it on the held order, and writes it to the invoice.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import sales_order
from klik_pos.api.sales_invoice import _parse_remarks, create_draft_invoice
from klik_pos.api.sales_order import checkout_held_order, create_held_order, get_held_order_details
from klik_pos.setup.pos_profile_fields import install_sales_order_remarks

CUSTOMER = "Walk In"
ITEM = "Consulting"


def _payload(**extra):
	return {
		"customer": {"id": CUSTOMER},
		"items": [{"id": ITEM, "item_code": ITEM, "name": ITEM, "quantity": 1, "price": 100, "uom": "Nos"}],
		"status": "held",
		**extra,
	}


def _so_remarks(name):
	return frappe.db.get_value("Sales Order", name, "remarks")


class TestSalesOrderHasRemarks(FrappeTestCase):
	def test_the_field_exists_and_installing_again_is_harmless(self):
		install_sales_order_remarks()
		install_sales_order_remarks()
		field = frappe.get_meta("Sales Order").get_field("remarks")
		self.assertTrue(field)
		self.assertEqual(field.fieldtype, "Small Text")


class TestRemarksTravel(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		install_sales_order_remarks()

	def test_a_held_order_keeps_its_remarks_and_a_recall_returns_them(self):
		held = create_held_order(_payload(remarks="  Deliver after 4pm  "))
		self.assertTrue(held["success"], held.get("message"))
		self.assertEqual(_so_remarks(held["order_name"]), "Deliver after 4pm")

		details = get_held_order_details(held["order_name"])
		self.assertEqual(details.get("remarks"), "Deliver after 4pm")

	def test_holding_again_replaces_or_clears_the_remarks(self):
		held = create_held_order(_payload(remarks="first"))
		create_held_order(_payload(remarks="second", held_order_id=held["order_name"]))
		self.assertEqual(_so_remarks(held["order_name"]), "second")
		create_held_order(_payload(remarks="", held_order_id=held["order_name"]))
		self.assertFalse(_so_remarks(held["order_name"]))

	def test_the_invoice_takes_the_remarks(self):
		draft = create_draft_invoice(_payload(remarks="Paid by cheque 0012"))
		self.assertTrue(draft["success"], draft.get("message"))
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["invoice_name"], "remarks"), "Paid by cheque 0012")

		create_draft_invoice(_payload(remarks="Paid by cheque 0013", draft_invoice_id=draft["invoice_name"]))
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["invoice_name"], "remarks"), "Paid by cheque 0013")

	def test_checking_out_a_held_order_carries_its_remarks_when_the_cart_sends_none(self):
		"""An older POS sends no remarks key: the held order's note still reaches the invoice."""
		held = create_held_order(_payload(remarks="Fragile"))
		with patch("klik_pos.api.sales_invoice._queue_sales_invoice", return_value={"success": False}) as queue, patch.object(
			sales_order, "_active_till", return_value=None
		):
			checkout_held_order(held["order_name"], {"checkout_request_id": None})
		self.assertEqual(queue.call_args.args[0].get("remarks"), "Fragile")


class TestParseRemarks(FrappeTestCase):
	def test_trims_strips_markup_and_caps(self):
		self.assertEqual(_parse_remarks({"remarks": "  <b>hi</b>  "}), "hi")
		# Ordinary text with angle brackets keeps its words; no tag can survive.
		self.assertEqual(_parse_remarks({"remarks": "Price < 100 and qty > 2"}), "Price 100 and qty 2")
		self.assertNotIn("<", _parse_remarks({"remarks": "<img src=x onerror=alert(1) "}))
		self.assertIsNone(_parse_remarks({"remarks": "   "}))
		self.assertIsNone(_parse_remarks({}))
		self.assertEqual(len(_parse_remarks({"remarks": "x" * 5000})), 2000)


class TestRemarksEdges(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		install_sales_order_remarks()

	def test_a_re_hold_from_a_pos_that_sends_no_remarks_keeps_them(self):
		held = create_held_order(_payload(remarks="Keep me"))
		payload = _payload(held_order_id=held["order_name"])
		self.assertNotIn("remarks", payload)
		create_held_order(payload)
		self.assertEqual(_so_remarks(held["order_name"]), "Keep me")

	def test_an_emptied_box_stops_the_held_order_s_note_reaching_the_invoice(self):
		held = create_held_order(_payload(remarks="Old note"))
		with patch("klik_pos.api.sales_invoice._queue_sales_invoice", return_value={"success": False}) as queue, patch.object(
			sales_order, "_active_till", return_value=None
		):
			checkout_held_order(held["order_name"], {"checkout_request_id": None, "remarks": ""})
		self.assertEqual(queue.call_args.args[0].get("remarks"), "")

	def test_submitting_a_draft_takes_the_remarks_even_with_no_other_data(self):
		"""The M-Pesa receipt-only submit sends no cart data; the note must still land."""
		from klik_pos.api.sales_invoice import submit_draft_invoice
		from klik_pos.tests.test_held_order_mpesa_checkout import _draft

		draft = _draft()
		frappe.db.set_value("Sales Invoice", draft.name, "remarks", "Typed before the receipts")
		result = submit_draft_invoice(draft.name, remarks="Typed after the receipts")
		self.assertTrue(result["success"], result)
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft.name, "remarks"), "Typed after the receipts")

	def test_an_emptied_box_clears_a_draft_s_remarks(self):
		from klik_pos.api.sales_invoice import submit_draft_invoice
		from klik_pos.tests.test_held_order_mpesa_checkout import _draft

		draft = _draft()
		frappe.db.set_value("Sales Invoice", draft.name, "remarks", "To be cleared")
		result = submit_draft_invoice(draft.name, remarks="")
		self.assertTrue(result["success"], result)
		self.assertIn(frappe.db.get_value("Sales Invoice", draft.name, "remarks") or "", ("", "No Remarks"))
