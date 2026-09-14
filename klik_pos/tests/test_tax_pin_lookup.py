"""The walk-in Tax ID lookup must help when cecypo_pin_checker is there and stay out of the
way when it is not. The KRA API is never called from these tests."""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from klik_pos.api import tax_pin

PIN = "P051189348K"


def _kra(name="JANE WANJIKU NA NA", status="Active", code="23000"):
	return {"ResponseCode": code, "PINDATA": {"Name": name, "StatusOfPIN": status}}


class TestTaxPinLookup(FrappeTestCase):
	def _lookup(self, response=None, raises=None, available=True):
		validate = MagicMock(return_value=response, side_effect=raises)
		with patch.object(tax_pin, "pin_checker_available", return_value=available), patch(
			"frappe.get_attr", return_value=validate
		):
			return tax_pin.lookup_tax_pin(PIN), validate

	def test_without_the_pin_checker_nothing_is_looked_up(self):
		result, validate = self._lookup(available=False)
		self.assertFalse(result["available"])
		self.assertFalse(result["success"])
		validate.assert_not_called()

	def test_an_active_pin_returns_the_registered_name_without_the_padding(self):
		result, _ = self._lookup(_kra())
		self.assertTrue(result["success"])
		self.assertEqual(result["name"], "JANE WANJIKU")
		self.assertEqual(result["status"], "Active")

	def test_an_inactive_pin_does_not_fill_a_name(self):
		result, _ = self._lookup(_kra(status="Dormant"))
		self.assertFalse(result["success"])
		self.assertEqual(result["name"], "")
		self.assertIn("Dormant", result["message"])

	def test_an_unknown_pin_says_so(self):
		result, _ = self._lookup({"ResponseCode": "80000"})
		self.assertFalse(result["success"])
		self.assertIn(PIN, result["message"])

	def test_an_api_failure_is_a_message_not_an_exception(self):
		result, _ = self._lookup(raises=Exception("timeout"))
		self.assertFalse(result["success"])
		self.assertTrue(result["message"])

	def test_a_malformed_pin_never_reaches_the_api(self):
		validate = MagicMock()
		with patch.object(tax_pin, "pin_checker_available", return_value=True), patch(
			"frappe.get_attr", return_value=validate
		):
			result = tax_pin.lookup_tax_pin("12345")
		self.assertFalse(result["success"])
		validate.assert_not_called()

	def test_availability_needs_the_app_installed(self):
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "klik_pos"]):
			self.assertFalse(tax_pin.pin_checker_available())

	def test_pos_details_report_availability(self):
		from klik_pos.api.pos_profile import get_pos_details

		with patch("klik_pos.api.pos_profile.pin_checker_available", return_value=False):
			self.assertEqual(get_pos_details()["pin_checker_available"], 0)
