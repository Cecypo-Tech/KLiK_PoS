"""The item list must resolve an item's tax template the way ERPNext does when it bills.

ERPNext looks at the Item's own tax rows, then walks up the Item Group tree, and only ever
considers enabled templates that belong to the transaction's company. The list only read the
Item's own rows and ignored company, so an item taxed through its group (Mixer -> Kenya Tax)
showed "No VAT" in the POS while its invoices were correctly taxed at 16%.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.api.item import item_listing

PARENT_GROUP = "TEST-GROUP-TAX-PARENT"
CHILD_GROUP = "TEST-GROUP-TAX-CHILD"
INHERITING_ITEM = "TEST-GROUP-TAX-ITEM-INHERITS"
OWN_TEMPLATE_ITEM = "TEST-GROUP-TAX-ITEM-OWN"
GROUP_TEMPLATE_TITLE = "TEST Group Tax 16"
OWN_TEMPLATE_TITLE = "TEST Own Tax 8"
OTHER_COMPANY_TEMPLATE_TITLE = "TEST Other Company Tax 30"


def _tax_account(company):
	return frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")


def _make_template(title, company, rate):
	existing = frappe.db.get_value("Item Tax Template", {"title": title, "company": company}, "name")
	if existing:
		return existing
	doc = frappe.new_doc("Item Tax Template")
	doc.title = title
	doc.company = company
	doc.append("taxes", {"tax_type": _tax_account(company), "tax_rate": rate})
	doc.insert(ignore_permissions=True)
	return doc.name


class TestItemGroupTaxInheritance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		companies = [
			c for c in frappe.get_all("Company", pluck="name", order_by="creation asc") if _tax_account(c)
		]
		if len(companies) < 2:
			raise cls.skipTest(cls, "needs two companies with a tax account")
		cls.company, cls.other_company = companies[0], companies[1]

		cls.group_template = _make_template(GROUP_TEMPLATE_TITLE, cls.company, 16)
		cls.own_template = _make_template(OWN_TEMPLATE_TITLE, cls.company, 8)
		cls.other_company_template = _make_template(OTHER_COMPANY_TEMPLATE_TITLE, cls.other_company, 30)

		if not frappe.db.exists("Item Group", PARENT_GROUP):
			parent = frappe.new_doc("Item Group")
			parent.item_group_name = PARENT_GROUP
			parent.parent_item_group = "All Item Groups"
			parent.is_group = 1
			# Listed first on purpose: a template for another company must be skipped, not picked.
			parent.append("taxes", {"item_tax_template": cls.other_company_template})
			parent.append("taxes", {"item_tax_template": cls.group_template})
			parent.insert(ignore_permissions=True)
		if not frappe.db.exists("Item Group", CHILD_GROUP):
			child = frappe.new_doc("Item Group")
			child.item_group_name = CHILD_GROUP
			child.parent_item_group = PARENT_GROUP
			child.is_group = 0
			child.insert(ignore_permissions=True)

		for code in (INHERITING_ITEM, OWN_TEMPLATE_ITEM):
			if frappe.db.exists("Item", code):
				continue
			item = frappe.new_doc("Item")
			item.item_code = code
			item.item_name = code
			item.item_group = CHILD_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			if code == OWN_TEMPLATE_ITEM:
				item.append("taxes", {"item_tax_template": cls.own_template})
			item.insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for code in (INHERITING_ITEM, OWN_TEMPLATE_ITEM):
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
		for group in (CHILD_GROUP, PARENT_GROUP):
			if frappe.db.exists("Item Group", group):
				frappe.delete_doc("Item Group", group, force=True, ignore_permissions=True)
		for title in (GROUP_TEMPLATE_TITLE, OWN_TEMPLATE_TITLE, OTHER_COMPANY_TEMPLATE_TITLE):
			for name in frappe.get_all("Item Tax Template", filters={"title": title}, pluck="name"):
				frappe.delete_doc("Item Tax Template", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _tax_info(self, item_code):
		pos_doc = frappe._dict(company=self.company, taxes_and_charges=None, is_tax_included_in_basic_rate=0)
		return item_listing._fetch_item_tax_info_map([item_code], pos_doc, frappe.utils.today())[item_code]

	def test_item_without_its_own_template_inherits_from_an_ancestor_group(self):
		info = self._tax_info(INHERITING_ITEM)

		self.assertEqual(info["item_tax_template"], self.group_template)
		self.assertEqual(info["total_tax_rate"], 16)
		self.assertTrue(info["has_vat"])

	def test_a_template_for_another_company_is_never_picked(self):
		self.assertNotEqual(self._tax_info(INHERITING_ITEM)["item_tax_template"], self.other_company_template)

	def test_the_items_own_template_wins_over_its_group(self):
		info = self._tax_info(OWN_TEMPLATE_ITEM)

		self.assertEqual(info["item_tax_template"], self.own_template)
		self.assertEqual(info["total_tax_rate"], 8)
