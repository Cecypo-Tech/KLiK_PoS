"""A KLiK Only user is sent from any desk address to the POS; everyone else is left alone."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.routing import RequestRedirect

from klik_pos.utils import before_request


class TestKlikOnlyRole(FrappeTestCase):
	def _visit(self, path, roles):
		with patch.object(frappe.local, "request", SimpleNamespace(path=path), create=True), patch(
			"klik_pos.utils.frappe.get_roles", return_value=roles
		):
			before_request()

	def test_a_pos_only_user_is_sent_to_the_pos_from_the_desk(self):
		for path in ("/desk", "/desk/sales-invoice", "/app", "/app/sales-invoice/SINV-1"):
			with self.assertRaises(RequestRedirect, msg=path) as hit:
				self._visit(path, ["Sales User", "KLiK Only"])
			self.assertTrue(hit.exception.new_url.endswith("/klik_pos"))

	def test_a_pos_only_user_still_reaches_the_pos_print_and_api(self):
		for path in ("/klik_pos", "/printview", "/api/method/ping", "/apps-like-page", "/desktop"):
			self._visit(path, ["Sales User", "KLiK Only"])

	def test_everyone_else_reaches_the_desk(self):
		self._visit("/desk/sales-invoice", ["Sales User", "System Manager"])
