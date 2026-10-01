"""The held-order row's Copy and Image icons.

Copy runs the site's own "Copy as Message" Client Script for Sales Order - the one the desk
form's Powerup menu runs, with whatever payment details the site wrote into it - so the
till hands the script to the SPA rather than keeping a second copy of the message. Image is
PowerPack's Copy as Image render. Each icon shows only when its source is there and on.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_order import get_held_order_share_tools

SCRIPT = "_Test KLiK Copy as Message (Sales Order)"
SOURCE = "frappe.ui.form.on('Sales Order', {refresh(frm) { frm.add_custom_button(__('Copy as Message'), () => 1); }});"


class TestHeldOrderShareTools(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# The site's own copy, if PowerPack seeded one, would answer first; keep it out.
		self._disabled = frappe.get_all(
			"Client Script", filters={"dt": "Sales Order", "enabled": 1}, pluck="name"
		)
		for name in self._disabled:
			frappe.db.set_value("Client Script", name, "enabled", 0)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _script(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "Client Script",
				"name": SCRIPT,
				"dt": "Sales Order",
				"view": "Form",
				"enabled": 1,
				"script": SOURCE,
				**overrides,
			}
		)
		doc.insert(ignore_permissions=True, set_name=SCRIPT)
		return doc

	def test_hands_over_the_site_s_copy_as_message_script(self):
		self._script()
		self.assertEqual(get_held_order_share_tools()["copy_message_script"], SOURCE)

	def test_a_disabled_script_offers_no_copy(self):
		self._script(enabled=0)
		self.assertIsNone(get_held_order_share_tools()["copy_message_script"])

	def test_another_sales_order_script_is_not_mistaken_for_it(self):
		self._script(script="frappe.ui.form.on('Sales Order', {refresh() {}});")
		self.assertIsNone(get_held_order_share_tools()["copy_message_script"])

	def test_a_script_for_another_doctype_is_not_used(self):
		self._script(dt="Sales Invoice")
		self.assertIsNone(get_held_order_share_tools()["copy_message_script"])

	def test_image_follows_powerpack_s_setting(self):
		with patch("klik_pos.api.sales_order._copy_as_image_enabled", return_value=True):
			self.assertTrue(get_held_order_share_tools()["copy_image"])
		with patch("klik_pos.api.sales_order._copy_as_image_enabled", return_value=False):
			self.assertFalse(get_held_order_share_tools()["copy_image"])

	def test_someone_who_cannot_read_sales_orders_gets_nothing(self):
		self._script()
		with patch("frappe.has_permission", return_value=False):
			self.assertEqual(
				get_held_order_share_tools(), {"copy_message_script": None, "copy_image": False}
			)
