"""The till's price is the price.

klik_pos built each invoice line with `rate` only, then let ERPNext re-run
set_missing_values and calculate_taxes_and_totals over it. Any matching Pricing
Rule made `calculate_item_rate` take the `if has_pricing_rules or not item.rate`
branch and replace the cashier's rate with price_list_rate * (1 - discount%).
On production that turned 20 x 2,000 into 20 x 2,205 = 44,100, and the customer
was charged the difference.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from klik_pos.api.sales_invoice import _get_active_pos_profile, build_sales_invoice_doc

ITEM_GROUP = "TEST-PRICE-AUTHORITY-GROUP"
ITEM_CODE = "TEST-PRICE-AUTHORITY-ITEM"
RULE_TITLE = "TEST-PRICE-AUTHORITY-RULE"

LIST_RATE = 2205.0
TILL_RATE = 2000.0
QTY = 20


class TestPosPriceAuthority(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pos_profile = _get_active_pos_profile()
		cls.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")

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
			item.insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": ITEM_CODE,
				"price_list": cls.pos_profile.selling_price_list,
				"selling": 1,
				"price_list_rate": LIST_RATE,
			}
		).insert(ignore_permissions=True)

		rule = frappe.new_doc("Pricing Rule")
		rule.title = RULE_TITLE
		rule.apply_on = "Item Code"
		rule.append("items", {"item_code": ITEM_CODE})
		rule.selling = 1
		rule.company = cls.pos_profile.company
		rule.currency = frappe.get_cached_value("Company", cls.pos_profile.company, "default_currency")
		rule.price_or_product_discount = "Price"
		rule.rate_or_discount = "Discount Percentage"
		rule.discount_percentage = 0
		rule.min_qty = QTY
		rule.priority = "1"
		rule.insert(ignore_permissions=True)
		cls.pricing_rule = rule.name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Pricing Rule", cls.pricing_rule):
			frappe.delete_doc("Pricing Rule", cls.pricing_rule, force=True, ignore_permissions=True)
		for name in frappe.get_all("Item Price", filters={"item_code": ITEM_CODE}, pluck="name"):
			frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", ITEM_CODE):
			frappe.delete_doc("Item", ITEM_CODE, force=True, ignore_permissions=True)
		if frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.delete_doc("Item Group", ITEM_GROUP, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _build(self, price_list_rate=None):
		item = {"id": ITEM_CODE, "quantity": QTY, "price": TILL_RATE, "uom": "Nos"}
		if price_list_rate is not None:
			item["price_list_rate"] = price_list_rate
		doc = build_sales_invoice_doc(
			self.customer, [item], 0, None, None, "B2C", include_payments=False
		)
		# build_sales_invoice_doc already ran set_missing_values and calculate_taxes_and_totals.
		# What a real checkout does next is doc.save() -> validate() -> set_missing_values with
		# for_validate=True; nothing calls the for_validate=False variant a second time. Mirror
		# that, so this asserts on the sequence production actually runs.
		doc.set_missing_values(for_validate=True)
		doc.calculate_taxes_and_totals()
		return doc

	def test_a_matching_pricing_rule_does_not_reprice_the_line(self):
		row = self._build().items[0]
		self.assertEqual(flt(row.rate), TILL_RATE)
		self.assertEqual(flt(row.amount), TILL_RATE * QTY)

	def test_the_payload_price_list_rate_is_what_the_invoice_records(self):
		row = self._build(price_list_rate=2100.0).items[0]
		self.assertEqual(flt(row.price_list_rate), 2100.0)
		self.assertEqual(flt(row.rate), TILL_RATE)

	def test_without_a_payload_price_list_rate_the_line_records_no_phantom_discount(self):
		row = self._build().items[0]
		self.assertEqual(flt(row.price_list_rate), TILL_RATE)
		self.assertEqual(flt(row.discount_amount), 0.0)

	def test_the_guard_throws_when_a_line_was_repriced(self):
		from klik_pos.api.sales_invoice import _assert_pos_rates_survived

		doc = self._build()
		expected = [(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in doc.items]
		doc.items[0].rate = LIST_RATE

		with self.assertRaises(frappe.ValidationError) as caught:
			_assert_pos_rates_survived(doc, expected)

		self.assertIn(ITEM_CODE, str(caught.exception))

	def test_the_guard_is_quiet_when_every_rate_held(self):
		from klik_pos.api.sales_invoice import _assert_pos_rates_survived

		doc = self._build()
		expected = [(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in doc.items]
		_assert_pos_rates_survived(doc, expected)

	def test_the_guard_skips_the_server_added_delivery_row(self):
		from klik_pos.api.sales_invoice import _assert_pos_rates_survived

		doc = self._build()
		expected = [(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in doc.items]
		doc.items[0].rate = LIST_RATE

		_assert_pos_rates_survived(doc, expected, skip_item_code=ITEM_CODE)

	def test_the_checkout_preview_returns_its_own_lines(self):
		from klik_pos.api.sales_invoice import validate_checkout_invoice

		result = validate_checkout_invoice(
			{
				"customer": {"id": self.customer},
				"items": [{"id": ITEM_CODE, "quantity": QTY, "price": TILL_RATE, "uom": "Nos"}],
				"status": "held",
			}
		)

		self.assertTrue(result["success"], result.get("message"))
		lines = result["tax_preview"]["items"]
		self.assertEqual(len(lines), 1)
		self.assertEqual(lines[0]["item_code"], ITEM_CODE)
		self.assertEqual(flt(lines[0]["qty"]), float(QTY))
		self.assertEqual(flt(lines[0]["rate"]), TILL_RATE)
		self.assertEqual(flt(lines[0]["amount"]), TILL_RATE * QTY)

	def test_reasserting_prices_leaves_the_delivery_row_alone(self):
		from klik_pos.api.sales_invoice import _reassert_pos_line_prices

		doc = self._build()
		pos_line_prices = [
			(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in doc.items
		]
		# _upsert_delivery_charge_service_item writes the keyed charge onto an existing cart
		# row when the delivery item is already in the cart. Restoring the till price by index
		# would put the cart rate back and lose the charge.
		doc.items[0].rate = 350.0

		_reassert_pos_line_prices(doc, pos_line_prices, skip_item_code=ITEM_CODE)

		self.assertEqual(flt(doc.items[0].rate), 350.0)

	def test_reasserting_prices_restores_every_other_row(self):
		from klik_pos.api.sales_invoice import _reassert_pos_line_prices

		doc = self._build()
		pos_line_prices = [
			(row.item_code, flt(row.rate), flt(row.price_list_rate)) for row in doc.items
		]
		doc.items[0].rate = LIST_RATE

		_reassert_pos_line_prices(doc, pos_line_prices)

		self.assertEqual(flt(doc.items[0].rate), TILL_RATE)


class TestCustomerPriceListDivergence(FrappeTestCase):
	"""The reported failure only happened once a customer account was selected.

	ERPNext's SalesInvoice.set_pos_fields (sales_invoice.py:1009-1023) switches
	`selling_price_list` to the CUSTOMER's default price list - or their customer
	group's - whenever a customer is set, falling back to the POS Profile's list only
	for Walk In. So the cart can price an item from one list while the server re-derives
	it from another, and only a named customer ever sees the difference.
	"""

	ITEM = "TEST-CUST-PRICELIST-ITEM"
	GROUP = "TEST-CUST-PRICELIST-GROUP"
	CONTRACT_LIST = "TEST-CUST-CONTRACT-LIST"
	CUSTOMER = "TEST-CUST-PRICELIST-CUSTOMER"

	TILL_RATE = 2000.0
	CONTRACT_RATE = 2205.0
	QTY = 20

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pos_profile = _get_active_pos_profile()

		if not frappe.db.exists("Item Group", cls.GROUP):
			frappe.get_doc({
				"doctype": "Item Group", "item_group_name": cls.GROUP,
				"parent_item_group": "All Item Groups", "is_group": 0,
			}).insert(ignore_permissions=True)

		if not frappe.db.exists("Item", cls.ITEM):
			item = frappe.new_doc("Item")
			item.item_code = cls.ITEM
			item.item_name = cls.ITEM
			item.item_group = cls.GROUP
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.is_sales_item = 1
			item.insert(ignore_permissions=True)

		if not frappe.db.exists("Price List", cls.CONTRACT_LIST):
			frappe.get_doc({
				"doctype": "Price List", "price_list_name": cls.CONTRACT_LIST,
				"selling": 1, "enabled": 1,
				"currency": frappe.get_cached_value("Company", cls.pos_profile.company, "default_currency"),
			}).insert(ignore_permissions=True)

		# The till's list says 2,000. The customer's contract list says 2,205.
		for price_list, rate in (
			(cls.pos_profile.selling_price_list, cls.TILL_RATE),
			(cls.CONTRACT_LIST, cls.CONTRACT_RATE),
		):
			existing = frappe.db.exists("Item Price", {"item_code": cls.ITEM, "price_list": price_list})
			if existing:
				frappe.db.set_value("Item Price", existing, "price_list_rate", rate)
			else:
				frappe.get_doc({
					"doctype": "Item Price", "item_code": cls.ITEM, "price_list": price_list,
					"selling": 1, "price_list_rate": rate,
				}).insert(ignore_permissions=True)

		if not frappe.db.exists("Customer", cls.CUSTOMER):
			frappe.get_doc({
				"doctype": "Customer", "customer_name": cls.CUSTOMER,
				"customer_type": "Company", "default_price_list": cls.CONTRACT_LIST,
			}).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Customer", cls.CUSTOMER, "default_price_list", cls.CONTRACT_LIST)

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for dt, name in (("Customer", cls.CUSTOMER), ("Item", cls.ITEM), ("Item Group", cls.GROUP)):
			if frappe.db.exists(dt, name):
				frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Item Price", filters={"item_code": cls.ITEM}, pluck="name"):
			frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Price List", cls.CONTRACT_LIST):
			frappe.delete_doc("Price List", cls.CONTRACT_LIST, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def _build(self, customer):
		doc = build_sales_invoice_doc(
			customer,
			[{"id": self.ITEM, "quantity": self.QTY, "price": self.TILL_RATE, "uom": "Nos"}],
			0, None, None, "B2C", include_payments=False,
		)
		doc.set_missing_values(for_validate=True)
		doc.calculate_taxes_and_totals()
		return doc

	def test_the_server_does_switch_to_the_customers_price_list(self):
		# Not the bug - just pinning the mechanism, so a future ERPNext change that
		# removes this override does not leave the test below passing for a stale reason.
		doc = self._build(self.CUSTOMER)
		self.assertEqual(doc.selling_price_list, self.CONTRACT_LIST)

	def test_a_customers_price_list_does_not_overrule_the_till(self):
		row = self._build(self.CUSTOMER).items[0]
		self.assertEqual(flt(row.rate), self.TILL_RATE)
		self.assertEqual(flt(row.amount), self.TILL_RATE * self.QTY)

	def test_a_customer_scoped_pricing_rule_does_not_overrule_the_till(self):
		"""The production shape: a rule that matches the account but not Walk In.

		A Pricing Rule with applicable_for="Customer" is why this was reported as
		"only when we select a customer account". Walk In never matches the rule, so
		calculate_item_rate leaves the till's rate alone and the sale is correct; the
		named customer matches it, `has_pricing_rules` goes true, and the rate is
		rebuilt from the price list behind the cashier.
		"""
		rule = frappe.new_doc("Pricing Rule")
		rule.title = "TEST-CUST-SCOPED-RULE"
		rule.apply_on = "Item Code"
		rule.append("items", {"item_code": self.ITEM})
		rule.selling = 1
		rule.applicable_for = "Customer"
		rule.customer = self.CUSTOMER
		rule.company = self.pos_profile.company
		rule.currency = frappe.get_cached_value("Company", self.pos_profile.company, "default_currency")
		rule.price_or_product_discount = "Price"
		rule.rate_or_discount = "Discount Percentage"
		rule.discount_percentage = 0
		rule.min_qty = self.QTY
		rule.priority = "1"
		rule.insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(
			lambda: (
				frappe.delete_doc("Pricing Rule", rule.name, force=True, ignore_permissions=True),
				frappe.db.commit(),
			)
		)

		row = self._build(self.CUSTOMER).items[0]
		self.assertEqual(flt(row.rate), self.TILL_RATE)
		self.assertEqual(flt(row.amount), self.TILL_RATE * self.QTY)
