import frappe
from frappe.tests import IntegrationTestCase

from klik_pos.testing import restore, snapshot


class TestTestingRestore(IntegrationTestCase):
	def test_settings_changed_by_the_bootstrap_come_back(self):
		saved = snapshot()
		self.assertIn(("System Settings", "time_zone"), saved)
		zone = saved[("System Settings", "time_zone")]
		frappe.db.set_single_value("System Settings", "time_zone", "Pacific/Fiji")
		restore(saved)
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), zone)
