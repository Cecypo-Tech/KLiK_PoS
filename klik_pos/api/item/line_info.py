"""What the grid till's side panel shows for the selected line, as the till's POS Profile lists it."""

import frappe
from frappe import _
from frappe.utils import cstr, flt, strip_html

from klik_pos.api.pos_profile import leaf_warehouses_for
from klik_pos.klik_pos.utils import get_current_pos_profile

# Computed facts; the SPA draws them. The cost ones still follow the till's Cost Display.
BUILTINS = {
	"in_stock": "In stock",
	"warehouses": "Warehouses",
	"valuation": "Valuation",
	"last_purchase": "Last purchase",
	"margin": "Margin",
	"uoms": "Units",
	"weight": "Weight",
}
DEFAULT_LINE_INFO = [
	"in_stock", "warehouses", "valuation", "last_purchase", "margin", "uoms", "weight",
	"description", "item_group", "brand",
]
# Fields with no value of their own to show.
_NO_VALUE = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect",
	"Image", "Fold", "Heading", "Attach Image", "Password",
}


def line_info_keys(entries):
	"""The till's list, blanks dropped; an empty list is the default list."""
	keys = [cstr(e).strip() for e in entries or [] if cstr(e).strip()]
	return keys or list(DEFAULT_LINE_INFO)


def _item_fields():
	return [df for df in frappe.get_meta("Item").fields if df.fieldtype not in _NO_VALUE]


@frappe.whitelist()
def get_line_info_choices():
	"""For the POS Profile form: what the list may hold, and the default list."""
	return {
		"builtins": [{"value": k, "label": _(v)} for k, v in BUILTINS.items()],
		"item_fields": [{"value": df.fieldname, "label": _(df.label or df.fieldname)} for df in _item_fields()],
		"defaults": DEFAULT_LINE_INFO,
	}


def _display(value, df, doc):
	if df.fieldtype == "Check":
		return _("Yes") if value else ""
	return strip_html(cstr(frappe.format_value(value, df, doc=doc))).strip()


def resolve_line_info(item_code, keys, company, user):
	frappe.has_permission("Item", "read", item_code, throw=True)
	item = frappe.get_doc("Item", item_code)
	meta = frappe.get_meta("Item")
	readable = set(meta.get_permlevel_access("read", user=user))

	rows = []
	for key in keys:
		if key in BUILTINS:
			rows.append({"key": key, "label": _(BUILTINS[key])})
			continue
		df = meta.get_field(key)
		if not df or df.fieldtype in _NO_VALUE or df.permlevel not in readable:
			continue
		value = item.get(key)
		shown = _display(value, df, item) if value not in (None, "") else ""
		if shown:
			rows.append({"key": key, "label": _(df.label or key), "value": shown})

	warehouses = []
	if "warehouses" in keys:
		allowed = leaf_warehouses_for(company, user)
		if allowed:
			warehouses = [
				{"warehouse": b.warehouse, "qty": flt(b.actual_qty)}
				for b in frappe.get_all(
					"Bin",
					filters={"item_code": item_code, "warehouse": ["in", allowed], "actual_qty": ["!=", 0]},
					fields=["warehouse", "actual_qty"],
					order_by="warehouse asc",
				)
			]

	uoms = []
	if "uoms" in keys:
		uoms = [
			{"uom": row.uom, "conversion_factor": flt(row.conversion_factor)}
			for row in item.uoms
			if row.uom != item.stock_uom
		]

	return {"rows": rows, "warehouses": warehouses, "uoms": uoms, "stock_uom": item.stock_uom}


@frappe.whitelist()
def get_line_info(item_code):
	"""The selected line's facts, as the caller's till lists them."""
	profile = get_current_pos_profile()
	keys = line_info_keys([row.info for row in profile.get("custom_line_info") or []])
	return resolve_line_info(item_code, keys, profile.company, frappe.session.user)
