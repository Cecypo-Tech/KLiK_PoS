"""The held-order row's Copy and Image icons.

Copy runs the site's own "Copy as Message" Client Script for Sales Order - the one the desk
form's Powerup menu runs, with whatever payment details the site wrote into it - so the
till hands the script to the SPA rather than keeping a second copy of the message. Image is
PowerPack's Copy as Image render. Each icon shows only when its source is there and on.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.sales_order import (
	POWERPACK_COPY_MESSAGE_SCRIPT,
	_copy_as_image_enabled,
	get_held_order_share_doc,
	get_held_order_share_tools,
)

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

	def _script(self, name=SCRIPT, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "Client Script",
				"name": name,
				"dt": "Sales Order",
				"view": "Form",
				"enabled": 1,
				"script": SOURCE,
				**overrides,
			}
		)
		doc.insert(ignore_permissions=True, set_name=name)
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

	def test_a_script_that_only_mentions_it_is_not_it(self):
		self._script(script="// TODO: Copy as Message\nfrappe.ui.form.on('Sales Order', {refresh() {}});")
		self.assertIsNone(get_held_order_share_tools()["copy_message_script"])

	def test_a_list_view_script_is_not_used(self):
		self._script(view="List")
		self.assertIsNone(get_held_order_share_tools()["copy_message_script"])

	def test_powerpack_s_own_script_wins_over_another_copy(self):
		self._script(name="_Test AAA earlier name", script=SOURCE.replace("() => 1", "() => 2"))
		if frappe.db.exists("Client Script", POWERPACK_COPY_MESSAGE_SCRIPT):
			frappe.db.set_value(
				"Client Script", POWERPACK_COPY_MESSAGE_SCRIPT, {"enabled": 1, "view": "Form", "script": SOURCE}
			)
		else:
			self._script(name=POWERPACK_COPY_MESSAGE_SCRIPT)
		self.assertEqual(get_held_order_share_tools()["copy_message_script"], SOURCE)

	def test_dates_follow_the_site_s_format(self):
		self.assertEqual(get_held_order_share_tools()["date_format"], frappe.db.get_default("date_format"))

	def test_image_follows_powerpack_s_setting(self):
		if "cecypo_powerpack" not in frappe.get_installed_apps():
			self.assertFalse(_copy_as_image_enabled())
			return
		with patch("cecypo_powerpack.utils.is_feature_enabled", return_value=True):
			self.assertTrue(get_held_order_share_tools()["copy_image"])
		with patch("cecypo_powerpack.utils.is_feature_enabled", return_value=False):
			self.assertFalse(get_held_order_share_tools()["copy_image"])

	def test_no_image_without_powerpack(self):
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "klik_pos"]):
			self.assertFalse(_copy_as_image_enabled())

	def test_someone_who_cannot_read_sales_orders_gets_nothing(self):
		self._script()
		user = "share-tools-no-read@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "NoRead", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		self.assertEqual(
			get_held_order_share_tools(), {"copy_message_script": None, "copy_image": False, "date_format": None}
		)
		order = frappe.get_all("Sales Order", limit=1, pluck="name", ignore_permissions=True)
		if order:
			with self.assertRaises(frappe.PermissionError):
				get_held_order_share_doc(order[0])

	def test_the_order_comes_with_its_currency_symbol(self):
		order = frappe.get_all("Sales Order", fields=["name", "currency"], limit=1)
		if not order:
			self.skipTest("no Sales Order on this site")
		result = get_held_order_share_doc(order[0].name)
		self.assertEqual(result["doc"]["name"], order[0].name)
		self.assertEqual(
			result["currency_symbol"],
			frappe.db.get_value("Currency", order[0].currency, "symbol") or order[0].currency,
		)
