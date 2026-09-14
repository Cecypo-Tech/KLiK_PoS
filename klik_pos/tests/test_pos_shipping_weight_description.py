"""Shipping rules, line descriptions and net weight on POS sales.

The till gained three things at once: a Shipping Rule picker at checkout, a pen on each cart
line that edits its description, and a net weight total. Each only matters if it reaches the
documents the till writes - the invoice, its checkout preview, and a held order - so that is
what these pin.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import (
	_get_active_pos_profile,
	build_sales_invoice_doc,
	validate_checkout_invoice,
)
from klik_pos.api.sales_order import create_held_order, get_held_order_details

ITEM_GROUP = "TEST-SHIP-WEIGHT-GROUP"
ITEM_CODE = "TEST-SHIP-WEIGHT-ITEM"
FIXED_RULE = "TEST-SHIP-FIXED"
WEIGHT_RULE = "TEST-SHIP-BY-WEIGHT"

ITEM_DESCRIPTION = "Standard catalogue description"
RATE = 100.0
WEIGHT_PER_UNIT = 5.0
FIXED_CHARGE = 150.0


def _company_account(company):
	return frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 0, "root_type": "Income", "disabled": 0},
		"name",
	)


class TestPosShippingWeightDescription(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pos_profile = _get_active_pos_profile()
		cls.company = cls.pos_profile.company
		cls.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
		cls.account = _company_account(cls.company)
		cls.cost_center = frappe.get_cached_value("Company", cls.company, "cost_center")

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": ITEM_GROUP,
					"parent_item_group": "All Item Groups",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = ITEM_CODE
			item.item_name = ITEM_CODE
			item.item_group = ITEM_GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.description = ITEM_DESCRIPTION
			item.weight_per_unit = WEIGHT_PER_UNIT
			item.weight_uom = "Kg" if frappe.db.exists("UOM", "Kg") else None
			item.insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": ITEM_CODE,
				"price_list": cls.pos_profile.selling_price_list,
				"selling": 1,
				"price_list_rate": RATE,
			}
		).insert(ignore_permissions=True)

		for name, based_on in ((FIXED_RULE, "Fixed"), (WEIGHT_RULE, "Net Weight")):
			if frappe.db.exists("Shipping Rule", name):
				frappe.delete_doc("Shipping Rule", name, force=True, ignore_permissions=True)
			rule = frappe.new_doc("Shipping Rule")
			rule.label = name
			rule.company = cls.company
			rule.account = cls.account
			rule.cost_center = cls.cost_center
			rule.shipping_rule_type = "Selling"
			rule.calculate_based_on = based_on
			if based_on == "Fixed":
				rule.shipping_amount = FIXED_CHARGE
			else:
				rule.append("conditions", {"from_value": 0, "to_value": 10, "shipping_amount": 50})
				rule.append("conditions", {"from_value": 10.001, "to_value": 0, "shipping_amount": 90})
			rule.insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for name in frappe.get_all(
			"Sales Order Item", filters={"item_code": ITEM_CODE}, pluck="parent", distinct=True
		):
			frappe.delete_doc("Sales Order", name, force=True, ignore_permissions=True)
		for name in (FIXED_RULE, WEIGHT_RULE):
			if frappe.db.exists("Shipping Rule", name):
				frappe.delete_doc("Shipping Rule", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Item Price", filters={"item_code": ITEM_CODE}, pluck="name"):
			frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", ITEM_CODE):
			frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
		if frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _item(self, qty=1, description=None):
		item = {"id": ITEM_CODE, "item_code": ITEM_CODE, "quantity": qty, "price": RATE, "uom": "Nos"}
		if description is not None:
			item["description"] = description
		return item

	def _build(self, items, **kwargs):
		doc = build_sales_invoice_doc(
			self.customer, items, 0, None, None, "B2C", include_payments=False, **kwargs
		)
		doc.set_missing_values(for_validate=True)
		doc.calculate_taxes_and_totals()
		return doc

	def _shipping_rows(self, doc):
		return [row for row in doc.taxes if row.account_head == self.account and row.charge_type == "Actual"]

	# Shipping rule -------------------------------------------------------------------------

	def test_a_fixed_shipping_rule_adds_its_charge_to_the_invoice(self):
		without = self._build([self._item()])
		doc = self._build([self._item()], shipping_rule=FIXED_RULE)

		self.assertEqual(doc.shipping_rule, FIXED_RULE)
		rows = self._shipping_rows(doc)
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0].tax_amount), FIXED_CHARGE)
		self.assertEqual(flt(doc.grand_total), flt(without.grand_total) + FIXED_CHARGE)

	def test_the_shipping_charge_does_not_reprice_the_lines(self):
		doc = self._build([self._item(qty=2)], shipping_rule=FIXED_RULE)
		self.assertEqual(flt(doc.items[0].rate), RATE)

	def test_a_net_weight_rule_charges_by_the_item_weight(self):
		light = self._build([self._item(qty=1)], shipping_rule=WEIGHT_RULE)  # 5 kg
		heavy = self._build([self._item(qty=3)], shipping_rule=WEIGHT_RULE)  # 15 kg

		self.assertEqual(flt(light.total_net_weight), WEIGHT_PER_UNIT)
		self.assertEqual(flt(self._shipping_rows(light)[0].tax_amount), 50.0)
		self.assertEqual(flt(heavy.total_net_weight), WEIGHT_PER_UNIT * 3)
		self.assertEqual(flt(self._shipping_rows(heavy)[0].tax_amount), 90.0)

	def test_a_shipping_rule_and_a_delivery_charge_cannot_both_be_charged(self):
		with self.assertRaises(frappe.ValidationError):
			self._build([self._item()], shipping_rule=FIXED_RULE, delivery_charge=40)

	def test_the_checkout_preview_reports_the_shipping_charge(self):
		result = validate_checkout_invoice(
			{
				"customer": {"id": self.customer},
				"items": [self._item()],
				"shipping_rule": FIXED_RULE,
				"status": "held",
			}
		)

		self.assertTrue(result["success"], result.get("message"))
		preview = result["tax_preview"]
		self.assertEqual(flt(preview["shipping_amount"]), FIXED_CHARGE)
		shipping = [row for row in preview["tax_breakdown"] if row["is_shipping"]]
		self.assertEqual(len(shipping), 1)
		self.assertEqual(flt(shipping[0]["tax_amount"]), FIXED_CHARGE)

	def test_the_checkout_preview_reports_the_net_weight(self):
		result = validate_checkout_invoice(
			{"customer": {"id": self.customer}, "items": [self._item(qty=3)], "status": "held"}
		)

		self.assertTrue(result["success"], result.get("message"))
		self.assertEqual(flt(result["tax_preview"]["total_net_weight"]), WEIGHT_PER_UNIT * 3)

	def test_the_till_lists_the_company_selling_rules(self):
		from klik_pos.api.shipping_rule import get_shipping_rules

		names = [row["name"] for row in get_shipping_rules()]

		self.assertIn(FIXED_RULE, names)
		self.assertIn(WEIGHT_RULE, names)

	# Line description ----------------------------------------------------------------------

	def test_the_cashier_description_is_written_to_the_invoice_line(self):
		doc = self._build([self._item(description="Gift wrap, deliver after 5pm")])
		self.assertEqual(doc.items[0].description, "Gift wrap, deliver after 5pm")

	def test_without_a_cashier_description_the_item_description_stays(self):
		doc = self._build([self._item()])
		self.assertEqual(doc.items[0].description, ITEM_DESCRIPTION)

	# Held order ----------------------------------------------------------------------------

	def test_a_held_order_keeps_the_description_and_the_shipping_rule(self):
		result = create_held_order(
			{
				"customer": {"id": self.customer},
				"items": [self._item(description="Leave at the gate")],
				"shipping_rule": FIXED_RULE,
				"status": "held",
			}
		)
		self.assertTrue(result["success"], msg=result.get("message"))

		details = get_held_order_details(result["order_name"])

		self.assertEqual(details["shipping_rule"], FIXED_RULE)
		self.assertEqual(details["items"][0]["description"], "Leave at the gate")

	# POS Profile ---------------------------------------------------------------------------

	def test_the_pos_profile_has_the_shipping_rule_toggle(self):
		from klik_pos.setup.pos_profile_fields import install_pos_profile_feature_fields

		install_pos_profile_feature_fields()

		self.assertTrue(frappe.db.has_column("POS Profile", "custom_enable_shipping_rule"))
