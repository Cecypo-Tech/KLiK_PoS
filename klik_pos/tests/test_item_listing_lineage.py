"""Tax inherited through item groups: every group's lineage in one nested-set query.

An item without its own Item Tax is taxed through its group, then the group's parents. The
listing used to look each group's ancestors up separately - 20 queries on dev's first page,
100+ on a parts catalogue with many groups - and to re-read every item's group although the
page query had just selected it.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.nestedset import get_ancestors_of

from klik_pos.api.item import item_listing
from klik_pos.tests.test_item_listing_group_tax import _make_template

ROOT = "TEST-LIN-ROOT"
MID = "TEST-LIN-MID"
LEAF = "TEST-LIN-LEAF"
ITEM = "TEST-LIN-ITEM"
TEMPLATE_TITLE = "TEST Lineage Tax 12"


class TestGroupLineage(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.db.get_value("Account", {"account_type": "Tax", "is_group": 0}, "company")
		if not company:
			raise cls.skipTest(cls, "needs a company with a tax account")
		cls.template = _make_template(TEMPLATE_TITLE, company, 12)
		for name, parent, is_group in ((ROOT, "All Item Groups", 1), (MID, ROOT, 1), (LEAF, MID, 0)):
			if not frappe.db.exists("Item Group", name):
				frappe.get_doc(
					{
						"doctype": "Item Group",
						"item_group_name": name,
						"parent_item_group": parent,
						"is_group": is_group,
						# The tax sits on ROOT alone: ITEM's group is two levels below it, so
						# ITEM reaches the tax only through its whole lineage.
						"taxes": [{"item_tax_template": cls.template}] if name == ROOT else [],
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": LEAF,
					"stock_uom": "Nos",
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Item", ITEM):
			frappe.delete_doc("Item", ITEM, force=True, ignore_permissions=True)
		for name in (LEAF, MID, ROOT):
			if frappe.db.exists("Item Group", name):
				frappe.delete_doc("Item Group", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Item Tax Template", filters={"title": TEMPLATE_TITLE}, pluck="name"):
			frappe.delete_doc("Item Tax Template", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def test_one_query_gives_the_lineage_get_ancestors_of_gives(self):
		self.assertEqual(
			item_listing._item_group_lineages([LEAF])[LEAF],
			[LEAF, *get_ancestors_of("Item Group", LEAF)],
		)

	def test_the_tax_rows_need_no_lookup_per_group(self):
		with patch("frappe.utils.nestedset.get_ancestors_of") as per_group:
			rows = item_listing._fetch_item_group_tax_rows([ITEM], group_by_item={ITEM: LEAF})
		per_group.assert_not_called()
		# The function answers [] when anything inside it fails, so "no lookup" alone could pass
		# on a broken query: ROOT's row must come back, at level 3 (LEAF 1, MID 2, ROOT 3).
		self.assertIn(
			(ITEM, 3, self.template),
			[(row["parent"], row["level"], row["item_tax_template"]) for row in rows],
		)

	def test_a_damaged_tree_cannot_cross_wire_tax_lineage(self):
		# Groups never put through the nested-set rebuild sit at lft = rgt = 0. Ancestry is strict,
		# as in get_ancestors_of, so such a group is nobody's parent; with <= / >= two of them
		# became each other's, and ITEM in LEAF was taxed with ROOT's template.
		self.addCleanup(frappe.db.rollback)
		frappe.db.sql("UPDATE `tabItem Group` SET lft = 0, rgt = 0 WHERE name IN (%s, %s)", (ROOT, LEAF))

		lineages = item_listing._item_group_lineages([ROOT, LEAF])
		self.assertEqual(lineages, {ROOT: [ROOT], LEAF: [LEAF]})
		self.assertEqual(lineages, {g: [g, *get_ancestors_of("Item Group", g)] for g in (ROOT, LEAF)})
		rows = item_listing._fetch_item_group_tax_rows([ITEM], group_by_item={ITEM: LEAF})
		self.assertNotIn(self.template, [row["item_tax_template"] for row in rows])
