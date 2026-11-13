"""Checkout email: the invoice goes out with the till's (or the picked) Email Template."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import email
from klik_pos.tests.test_held_order_visibility import CUSTOMER, ITEM
from klik_pos.tests.test_opening_conflict import _profile, _shift


def _template(name, subject, body):
	if not frappe.db.exists("Email Template", name):
		frappe.get_doc({"doctype": "Email Template", "name": name, "subject": subject, "response": body}).insert()
	return name


class TestInvoiceEmail(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.profile = _profile()
		_shift(self.profile, "Administrator")
		si = frappe.new_doc("Sales Invoice")
		si.customer = CUSTOMER
		si.company = frappe.db.get_value("POS Profile", self.profile, "company")
		si.append("items", {"item_code": ITEM, "qty": 1, "rate": 50})
		si.insert(ignore_permissions=True, ignore_mandatory=True)
		self.si = si.name

	def _send(self, **kw):
		with patch("frappe.sendmail") as send, patch("frappe.get_print", return_value=b"%PDF"):
			email.send_invoice_email(email="a@x.com", invoice_data=self.si, customer_name="Ann", **kw)
		return send.call_args.kwargs

	def test_profile_template_gives_subject_and_body(self):
		frappe.db.set_value("POS Profile", self.profile, "custom_email_template",
			_template("_Test Inv Mail", "Invoice {{ doc.name }}", "Total {{ doc.grand_total }}"))
		kw = self._send()
		self.assertEqual(kw["subject"], f"Invoice {self.si}")
		self.assertIn("Total 50", kw["message"])

	def test_picked_template_beats_the_profile_and_the_cashier_text_is_sent(self):
		frappe.db.set_value("POS Profile", self.profile, "custom_email_template",
			_template("_Test Inv Mail", "Invoice {{ doc.name }}", "x"))
		_template("_Test Inv Other", "Other {{ doc.name }}", "y")
		kw = self._send(template="_Test Inv Other", message="Hi Ann, ref {{ doc.name }}")
		self.assertEqual(kw["subject"], f"Other {self.si}")
		self.assertEqual(kw["message"], f"Hi Ann, ref {self.si}")

	def test_cashier_text_that_is_not_valid_jinja_is_sent_as_typed(self):
		frappe.db.set_value("POS Profile", self.profile, "custom_email_template", None)
		kw = self._send(message="Price {{ oops")
		self.assertEqual(kw["message"], "Price {{ oops")
		self.assertIn(self.si, kw["subject"])
