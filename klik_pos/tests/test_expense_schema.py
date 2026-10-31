import frappe
from frappe.tests.utils import FrappeTestCase


class TestExpenseSchema(FrappeTestCase):
	def test_fields_exist(self):
		for dt, fields in {
			"POS Profile": [
				"custom_expense_account",
				"custom_expenses_need_approval",
				"custom_expense_types",
			],
			"POS Profile User": ["custom_can_record_expenses"],
			"Journal Entry": [
				"custom_pos_profile",
				"custom_warehouse",
				"custom_pos_opening_entry",
				"custom_expense_type",
			],
		}.items():
			meta = frappe.get_meta(dt)
			for f in fields:
				self.assertTrue(meta.has_field(f), f"{dt}.{f} missing")

	def test_expense_type_doctype(self):
		self.assertTrue(frappe.db.exists("DocType", "POS Profile Expense Type"))
		meta = frappe.get_meta("POS Profile Expense Type")
		self.assertEqual(
			meta.get_field("expense_account").link_filters,
			'[["Account","is_group","=",0],["Account","root_type","=","Expense"]]',
		)
