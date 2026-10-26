"""Frappe 16 lists owner among its standard set-once fields (Meta.standard_set_once_fields).
_mark_invoice_queued reassigned it, so a draft queued by anyone but its cashier failed to
save with 'Value cannot be changed for Created By' (Allparts CS-03875, 2026-10-26)."""

import frappe

from klik_pos.api.sales_invoice import _mark_invoice_queued
from klik_pos.tests.test_stock_reservation import ITEM_CODE, StockReservationTestCase


class TestQueuingKeepsTheOwner(StockReservationTestCase):
	def test_an_existing_draft_queued_by_another_user_saves(self):
		doc = self._draft_invoice(queue_status=None)
		cashier = doc.owner

		_mark_invoice_queued(doc, "someone.else@example.com")
		doc.save(ignore_permissions=True)  # raised CannotChangeConstantError before the fix

		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "owner"), cashier)
		self.assertEqual(doc.queue_status, "Queued")

	def test_a_new_invoice_is_owned_by_the_session_user(self):
		doc = frappe.new_doc("Sales Invoice")
		doc.customer = self.customer
		doc.company = self.company
		doc.append("items", {"item_code": ITEM_CODE, "qty": 1, "rate": 10, "warehouse": self.warehouse})

		_mark_invoice_queued(doc, frappe.session.user)
		doc.insert(ignore_permissions=True)
		self.addCleanup(self._purge_invoice, doc.name)

		self.assertEqual(doc.owner, frappe.session.user)
