"""Loss of Sale: when a line asks for more than the warehouse holds, sell what is there and
record the rest on the line as custom_los_qty. Requested = qty + custom_los_qty, so a split can
run again - stock may have moved - without losing what the customer asked for."""

import math

import frappe
from frappe import _
from frappe.utils import cint, flt

LOS_FIELD = "custom_los_qty"
PROFILE_FLAG = "custom_enable_loss_of_sale"


def split_lines(lines, available):
	"""Fill lines in order from shared stock.

	lines: dicts with key (item_code, warehouse), requested (in the line's UOM), factor (stock
	units per line unit) and whole (the line's UOM takes whole numbers only). available:
	{key: stock units}; a key not in it has none. Returns [(qty, los_qty)] in line order."""
	left = {key: max(flt(qty), 0) for key, qty in available.items()}
	result = []
	for line in lines:
		requested = max(flt(line["requested"]), 0)
		factor = flt(line.get("factor")) or 1
		qty = min(requested, left.get(line["key"], 0) / factor)
		if line.get("whole"):
			qty = math.floor(qty + 1e-9)
		qty = flt(qty, 9)
		left[line["key"]] = left.get(line["key"], 0) - qty * factor
		result.append((qty, flt(requested - qty, 9)))
	return result


def split_cart_items(items, pos_profile):
	"""The till's cart lines, as parse_invoice_data returns them, split in place against the
	till's warehouse. Returns one {index, item_code, quantity, los_qty} per line it changed.
	Runs before the invoice is built: the builder checks batch stock against these quantities."""
	if not cint(pos_profile.get(PROFILE_FLAG)):
		for item in items:
			item["los_qty"] = 0
		return []

	from erpnext.stock.get_item_details import get_conversion_factor

	warehouse = pos_profile.warehouse
	eligible = _eligible_item_codes({item["id"] for item in items})
	whole = _whole_number_uoms(item.get("uom") for item in items)
	picked = [
		(index, item)
		for index, item in enumerate(items)
		if item["id"] in eligible and not item.get("bundle_entries")
	]
	if not picked or not warehouse:
		return []

	lines = [
		{
			"key": (item["id"], warehouse),
			"requested": flt(item.get("quantity")) + flt(item.get("los_qty")),
			"factor": flt((get_conversion_factor(item["id"], item.get("uom")) or {}).get("conversion_factor"))
			if item.get("uom")
			else 1,
			"whole": item.get("uom") in whole,
		}
		for _index, item in picked
	]
	available = _available({line["key"] for line in lines})

	changes = []
	for (index, item), (qty, los_qty) in zip(picked, split_lines(lines, available)):
		if qty != flt(item.get("quantity")) or los_qty != flt(item.get("los_qty")):
			changes.append({"index": index, "item_code": item["id"], "quantity": qty, "los_qty": los_qty})
		item["quantity"] = qty
		item["los_qty"] = los_qty
	_refuse_if_nothing_sold([item.get("quantity") for item in items])
	return changes


def fold_los_into_quantity(items):
	"""A held order is a Sales Order, which refuses qty-0 lines: hold what was asked for and let
	checkout split it against the stock there is then."""
	for item in items:
		item["quantity"] = flt(item.get("quantity")) + flt(item.get("los_qty"))
		item["los_qty"] = 0
	return items


def _eligible_item_codes(item_codes):
	"""Stock items that may not go negative and carry no serial numbers: the lines Loss of Sale
	may shorten. A product bundle is not a stock item, so it is never one of them."""
	if not item_codes:
		return set()
	return set(
		frappe.get_all(
			"Item",
			filters={
				"name": ["in", list(item_codes)],
				"is_stock_item": 1,
				"allow_negative_stock": 0,
				"has_serial_no": 0,
			},
			pluck="name",
		)
	)


def _whole_number_uoms(uoms):
	uoms = list({uom for uom in uoms if uom})
	if not uoms:
		return set()
	return set(frappe.get_all("UOM", filters={"name": ["in", uoms], "must_be_whole_number": 1}, pluck="name"))


def _available(keys, exclude_invoice=None):
	from klik_pos.api.sales_invoice import get_available_stock_map

	return {key: row.available_qty for key, row in get_available_stock_map(keys, exclude_invoice).items()}


def _refuse_if_nothing_sold(quantities):
	if quantities and not any(flt(qty) > 0 for qty in quantities):
		frappe.throw(_("Nothing on this sale is in stock."), title=_("Loss of Sale"))
