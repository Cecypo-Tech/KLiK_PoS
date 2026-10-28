"""A refusal reaches the cashier unlogged, as Frappe does - unless it was raised while handling
another exception. Then it is hiding the failure that matters: a close that ERPNext rolled back
over a PermissionError reached the till only as "Could not find Reference Name: POS-CLO-...",
and nothing kept the PermissionError."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from klik_pos.api import pos_entry

CLOSING = "POS Closing Entry Creation Failed"
OPENING = "POS Opening Entry Creation Failed"


def _masked(*args):
	"""A ValidationError raised while handling a PermissionError, as create_merge_logs does."""
	try:
		raise frappe.PermissionError("no write on POS Opening Entry")
	except frappe.PermissionError:
		frappe.throw("Could not find Reference Name: POS-CLO-TEST", frappe.LinkValidationError)


def _plain(*args):
	frappe.throw("A manager must close this till.")


def _logs(title):
	return frappe.db.count("Error Log", {"method": title})


class TestMaskedFailureLogging(IntegrationTestCase):
	def _close(self, failure):
		shift = frappe._dict(name="POS-OPE-TEST", pos_profile="Till", user="Administrator")
		with (
			patch.object(pos_entry, "_parse_request_data", return_value={}),
			patch.object(pos_entry, "_get_open_pos_entry", return_value=shift),
			patch.object(pos_entry, "ensure_may_close_on_till"),
			patch.object(pos_entry, "_ensure_may_close"),
			patch.object(pos_entry, "_calculate_payment_reconciliation", return_value=[]),
			patch.object(pos_entry, "_create_and_submit_closing_doc", side_effect=failure),
		):
			pos_entry.create_closing_entry()

	def _open(self, failure):
		frappe.local.form_dict = frappe._dict(pos_profile="Till", balance_details=[{"mode_of_payment": "Cash"}])
		with (
			patch.object(frappe.db, "get_value", return_value="Company"),
			patch.object(pos_entry, "opening_conflict", side_effect=failure),
		):
			pos_entry.create_opening_entry()

	def test_a_close_that_hides_a_failure_is_logged_with_it(self):
		before = _logs(CLOSING)
		with self.assertRaises(frappe.LinkValidationError):
			self._close(_masked)
		self.assertEqual(_logs(CLOSING), before + 1)
		log = frappe.get_last_doc("Error Log", filters={"method": CLOSING})
		self.assertIn("no write on POS Opening Entry", log.error, "the hidden failure is kept")

	def test_a_plain_refusal_to_close_is_not_logged(self):
		before = _logs(CLOSING)
		with self.assertRaises(frappe.ValidationError):
			self._close(_plain)
		self.assertEqual(_logs(CLOSING), before)

	def test_an_opening_that_hides_a_failure_is_logged_with_it(self):
		before = _logs(OPENING)
		with self.assertRaises(frappe.LinkValidationError):
			self._open(_masked)
		self.assertEqual(_logs(OPENING), before + 1)

	def test_a_plain_refusal_to_open_is_not_logged(self):
		before = _logs(OPENING)
		with self.assertRaises(frappe.ValidationError):
			self._open(_plain)
		self.assertEqual(_logs(OPENING), before)

	def test_a_permission_error_names_itself_to_the_cashier(self):
		# str(PermissionError()) is "", so the till read "Failed to create POS Opening Entry: ".
		with self.assertRaisesRegex(frappe.ValidationError, "Failed to create POS Opening Entry: .+"):
			self._open(frappe.PermissionError)
