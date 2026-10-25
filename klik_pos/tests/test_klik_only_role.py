"""A KLiK Only user is sent from any desk address to the POS; everyone else is left alone."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.routing import RequestRedirect

from klik_pos.utils import before_request


class TestKlikOnlyRole(FrappeTestCase):
	def _visit(self, path, roles):
		# Any user but Administrator; the roles are patched in.
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")
		with (
			patch.object(frappe.local, "request", SimpleNamespace(path=path), create=True),
			patch("klik_pos.utils.frappe.get_roles", return_value=roles),
		):
			before_request()

	def test_a_pos_only_user_is_sent_to_the_pos_from_the_desk(self):
		for path in ("/desk", "/desk/sales-invoice", "/app", "/app/sales-invoice/SINV-1"):
			with self.assertRaises(RequestRedirect, msg=path) as hit:
				self._visit(path, ["Sales User", "KLiK Only"])
			self.assertTrue(hit.exception.new_url.endswith("/klik_pos"))
			# Temporary, so a browser does not remember it once the role is taken away.
			self.assertEqual(hit.exception.code, 302)

	def test_a_pos_only_user_still_reaches_the_pos_print_and_api(self):
		for path in ("/klik_pos", "/printview", "/api/method/ping", "/apps-like-page", "/desktop"):
			self._visit(path, ["Sales User", "KLiK Only"])

	def test_everyone_else_reaches_the_desk(self):
		self._visit("/desk/sales-invoice", ["Sales User", "System Manager"])

	def test_administrator_reaches_the_desk_although_it_holds_every_role(self):
		self.assertIn("KLiK Only", frappe.get_roles("Administrator"))
		frappe.set_user("Administrator")
		with patch.object(frappe.local, "request", SimpleNamespace(path="/desk"), create=True):
			before_request()

	def test_migrate_leaves_a_disabled_role_disabled(self):
		from klik_pos.utils import POS_ONLY_ROLE, ensure_pos_only_role

		ensure_pos_only_role()
		frappe.db.set_value("Role", POS_ONLY_ROLE, "disabled", 1)
		self.addCleanup(frappe.db.set_value, "Role", POS_ONLY_ROLE, "disabled", 0)
		ensure_pos_only_role()
		self.assertEqual(frappe.db.get_value("Role", POS_ONLY_ROLE, "disabled"), 1)

	def test_a_system_manager_reaches_the_desk_even_with_the_role(self):
		self._visit("/desk/sales-invoice", ["Sales User", "KLiK Only", "System Manager"])
