import frappe
from frappe.tests.utils import FrappeTestCase


class TestCsrfToken(FrappeTestCase):
	def test_returns_the_sessions_own_token(self):
		"""The till keeps the token its page was rendered with; after a login elsewhere the
		session holds another, and every save fails "Invalid Request" until it asks again."""
		from klik_pos.api.user import csrf_token

		out = csrf_token()
		self.assertTrue(out["token"])
		self.assertEqual(out["token"], frappe.session.data.csrf_token)
		self.assertEqual(out["user"], frappe.session.user)
