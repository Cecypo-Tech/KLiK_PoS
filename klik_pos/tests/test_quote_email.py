"""Quote Saved dialog: email the quote PDF, prefilled from the quote's contact and customer."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api import quotation
from klik_pos.setup.quote_fields import ensure_quote_fields
from klik_pos.tests.test_held_order_visibility import CUSTOMER, ITEM
from klik_pos.tests.test_opening_conflict import _profile, _shift
from klik_pos.tests.test_till_quote import _payload


class TestQuoteEmail(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_quote_fields()
		self.addCleanup(frappe.db.rollback)
		self.profile = _profile()
		_shift(self.profile, "Administrator")
		self.quote = quotation.create_quote(_payload(ITEM, qty=1, rate=100))["quote_name"]

	def test_recipients_are_the_contact_then_the_customer_without_repeats(self):
		frappe.db.set_value("Customer", CUSTOMER, "email_id", "Buyer@Example.com")
		frappe.db.set_value("Quotation", self.quote, "contact_email", "ops@example.com")
		self.assertEqual(quotation.get_quote_emails(self.quote), ["ops@example.com", "Buyer@Example.com"])
		frappe.db.set_value("Quotation", self.quote, "contact_email", "buyer@example.com")
		self.assertEqual(quotation.get_quote_emails(self.quote), ["buyer@example.com"])

	def test_sends_pdf_to_every_address_with_the_profile_template(self):
		tpl = frappe.get_doc({
			"doctype": "Email Template", "name": "_Test Quote Mail",
			"subject": "Quote {{ doc.name }}", "response": "Hello {{ doc.customer_name }}",
		}).insert(ignore_if_duplicate=True)
		frappe.db.set_value("POS Profile", self.profile, "custom_email_template", tpl.name)
		with patch("frappe.sendmail") as send, patch("frappe.get_print", return_value=b"%PDF"):
			res = quotation.send_quote_email(self.quote, "a@x.com, b@x.com ;a@x.com")
		kw = send.call_args.kwargs
		self.assertEqual(kw["recipients"], ["a@x.com", "b@x.com"])
		self.assertEqual(kw["subject"], f"Quote {self.quote}")
		self.assertIn(frappe.db.get_value("Quotation", self.quote, "customer_name"), kw["message"])
		self.assertEqual(kw["attachments"][0]["fname"], f"{self.quote}.pdf")
		self.assertEqual((kw["reference_doctype"], kw["reference_name"]), ("Quotation", self.quote))
		self.assertEqual(res["recipients"], ["a@x.com", "b@x.com"])

	def test_without_a_template_a_plain_message_goes(self):
		frappe.db.set_value("POS Profile", self.profile, "custom_email_template", None)
		with patch("frappe.sendmail") as send, patch("frappe.get_print", return_value=b"%PDF"):
			quotation.send_quote_email(self.quote, "a@x.com")
		self.assertIn(self.quote, send.call_args.kwargs["subject"])

	def test_bad_or_missing_address_is_refused(self):
		with patch("frappe.sendmail") as send:
			self.assertRaises(frappe.ValidationError, quotation.send_quote_email, self.quote, "")
			self.assertRaises(frappe.ValidationError, quotation.send_quote_email, self.quote, "not-an-email")
		send.assert_not_called()
