"""Items for the listing tests: one group, two warehouses, one item of every kind the till
filters on - stocked, empty, stocked only elsewhere, negative stock allowed, service,
variant template, bundle (renamed to a series-style name, as this site names bundles) and
three items sharing one name.
"""

import frappe

GROUP = "TEST-LISTQ-GROUP"
COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
OTHER_WAREHOUSE = "_Test Warehouse 1 - _TC"

STOCKED = "LISTQ-STOCKED"
EMPTY = "LISTQ-EMPTY"
ELSEWHERE = "LISTQ-ELSEWHERE"
NEGATIVE = "LISTQ-NEGATIVE"
SERVICE = "LISTQ-SERVICE"
TEMPLATE = "LISTQ-TEMPLATE"
BUNDLE = "LISTQ-BUNDLE"
BUNDLE_DOC_NAME = "PB-LISTQ-BUNDLE-001"
TWINS = ["LISTQ-TWIN-A", "LISTQ-TWIN-B", "LISTQ-TWIN-C"]
TWIN_NAME = "LISTQ TWIN"

EVERY = [STOCKED, EMPTY, ELSEWHERE, NEGATIVE, SERVICE, TEMPLATE, BUNDLE, *TWINS]


def pos_context(hide_unavailable, warehouse=WAREHOUSE, include_service_items=0, enhanced_search=0):
	"""What item_listing._get_pos_context returns, pinned for a test."""
	pos_doc = frappe._dict(
		name="TEST-LISTQ-PROFILE",
		company=COMPANY,
		warehouse=warehouse,
		selling_price_list="_Test Price List",
		item_groups=[],
		custom_enable_service_items=include_service_items,
		custom_enhanced_search=enhanced_search,
		is_tax_included_in_basic_rate=0,
		taxes_and_charges=None,
	)
	return pos_doc, warehouse, pos_doc.selling_price_list, hide_unavailable


def _item(code, name=None, **fields):
	if frappe.db.exists("Item", code):
		return
	doc = frappe.new_doc("Item")
	doc.item_code = code
	doc.item_name = name or code
	doc.item_group = GROUP
	doc.stock_uom = "Nos"
	doc.is_stock_item = fields.pop("is_stock_item", 1)
	doc.is_sales_item = 1
	doc.update(fields)
	doc.insert(ignore_permissions=True)


def _bin(code, warehouse, qty, valuation_rate=0):
	name = frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "name")
	if not name:
		name = (
			frappe.get_doc({"doctype": "Bin", "item_code": code, "warehouse": warehouse})
			.insert(ignore_permissions=True)
			.name
		)
	frappe.db.set_value(
		"Bin", name, {"actual_qty": qty, "valuation_rate": valuation_rate}, update_modified=False
	)


def make_listing_fixtures():
	if not frappe.db.exists("Item Group", GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

	_item(STOCKED)
	_bin(STOCKED, WAREHOUSE, 5, valuation_rate=12.5)
	_item(EMPTY)
	_bin(EMPTY, WAREHOUSE, 0)
	_item(ELSEWHERE)
	_bin(ELSEWHERE, OTHER_WAREHOUSE, 5)
	_item(NEGATIVE, allow_negative_stock=1)
	_item(SERVICE, is_stock_item=0)
	_item(TEMPLATE, is_stock_item=0)
	# A real variant template needs attributes to save; the listing only reads has_variants.
	frappe.db.set_value("Item", TEMPLATE, "has_variants", 1)
	_item(BUNDLE, is_stock_item=0)
	bundle = frappe.db.get_value("Product Bundle", {"new_item_code": BUNDLE}, "name")
	if not bundle:
		bundle = (
			frappe.get_doc(
				{
					"doctype": "Product Bundle",
					"new_item_code": BUNDLE,
					"items": [{"item_code": STOCKED, "qty": 1}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	if bundle != BUNDLE_DOC_NAME:
		# Whatever this site's naming does, the bundle's own name is not its item code -
		# the case a join on the bundle's name would miss.
		frappe.rename_doc("Product Bundle", bundle, BUNDLE_DOC_NAME, force=True)
	for code in TWINS:
		_item(code, name=TWIN_NAME)
	frappe.db.commit()


def drop_listing_fixtures():
	for bundle in frappe.get_all("Product Bundle", filters={"new_item_code": BUNDLE}, pluck="name"):
		frappe.delete_doc("Product Bundle", bundle, force=True, ignore_permissions=True)
	for code in EVERY:
		for bin_name in frappe.get_all("Bin", filters={"item_code": code}, pluck="name"):
			frappe.db.set_value("Bin", bin_name, "actual_qty", 0, update_modified=False)
			frappe.delete_doc("Bin", bin_name, force=True, ignore_permissions=True)
		if frappe.db.exists("Item", code):
			frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
	if frappe.db.exists("Item Group", GROUP):
		frappe.delete_doc("Item Group", GROUP, force=True, ignore_permissions=True)
	frappe.db.commit()
