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


def in_stock_total(grand_total, lines, available):
	"""What a held order would come to if checked out now: its total, scaled by the share of its
	value in stock, so tax and discounts scale with it. lines: split_lines' lines plus rate, and
	eligible (False: a line Loss of Sale may not shorten, which sells as asked)."""
	split = iter(split_lines([line for line in lines if line["eligible"]], available))
	asked = now = 0
	for line in lines:
		qty = next(split)[0] if line["eligible"] else flt(line["requested"])
		asked += flt(line["requested"]) * flt(line["rate"])
		now += qty * flt(line["rate"])
	return flt(grand_total) * now / asked if asked else flt(grand_total)


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
	# A line Loss of Sale may not touch (batch, serial, bundle) sells what was asked for and
	# meets the normal stock check: the till can mark one when a scan left its flags unknown.
	changes = []
	picked_indexes = {index for index, _item in picked}
	for index, item in enumerate(items):
		if index not in picked_indexes and flt(item.get("los_qty")):
			item["quantity"] = flt(item.get("quantity")) + flt(item.get("los_qty"))
			item["los_qty"] = 0
			changes.append({"index": index, "item_code": item["id"], "quantity": item["quantity"], "los_qty": 0})
	if not picked or not warehouse:
		return changes

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

	for (index, item), (qty, los_qty) in zip(picked, split_lines(lines, available)):
		if qty != flt(item.get("quantity")) or los_qty != flt(item.get("los_qty")):
			changes.append({"index": index, "item_code": item["id"], "quantity": qty, "los_qty": los_qty})
		item["quantity"] = qty
		item["los_qty"] = los_qty
	_refuse_if_nothing_sold([item.get("quantity") for item in items])
	return sorted(changes, key=lambda change: change["index"])


def fold_los_into_quantity(items):
	"""A held order is a Sales Order, which refuses qty-0 lines: hold what was asked for and let
	checkout split it against the stock there is then."""
	for item in items:
		item["quantity"] = flt(item.get("quantity")) + flt(item.get("los_qty"))
		item["los_qty"] = 0
	return items


def _eligible_item_codes(item_codes):
	"""Stock items that may not go negative and carry no serial or batch numbers: the lines Loss
	of Sale may shorten. A product bundle is not a stock item, so it is never one of them."""
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
				"has_batch_no": 0,
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


def split_invoice_rows(doc):
	"""A Sales Invoice's own rows, split in place. Returns one
	{idx, item_code, from_qty, qty, los_qty} per row it changed; from_qty is what was asked for."""
	rows = [row for row in doc.items if row.item_code and row.warehouse]
	eligible = _eligible_item_codes({row.item_code for row in rows})
	whole = _whole_number_uoms(row.uom for row in rows)
	picked = [
		row
		for row in rows
		if row.item_code in eligible
		and not (row.get("serial_and_batch_bundle") or row.get("batch_no") or row.get("serial_no"))
	]
	if not picked:
		return []

	lines = [
		{
			"key": (row.item_code, row.warehouse),
			"requested": flt(row.qty) + flt(row.get(LOS_FIELD)),
			"factor": flt(row.conversion_factor) or 1,
			"whole": row.uom in whole,
		}
		for row in picked
	]
	available = _available({line["key"] for line in lines}, exclude_invoice=None if doc.is_new() else doc.name)

	changes = []
	for row, line, (qty, los_qty) in zip(picked, lines, split_lines(lines, available)):
		if qty != flt(row.qty) or los_qty != flt(row.get(LOS_FIELD)):
			changes.append(
				{"idx": row.idx, "item_code": row.item_code, "from_qty": line["requested"], "qty": qty, "los_qty": los_qty}
			)
		row.qty = qty
		row.set(LOS_FIELD, los_qty)
		row.stock_qty = flt(qty * line["factor"])
	_refuse_if_nothing_sold([row.qty for row in doc.items])
	return changes


def before_validate(doc, method=None):
	"""Sales Invoice doc_event. On submit of an unpaid stock invoice whose till records Loss of
	Sale, shorten lines to the stock there is instead of ERPNext refusing with 'units needed'.
	A paid invoice is left alone: shortening it would leave money unaccounted for. So is a till
	invoice: the till split its cart before building it, and shortening it later (in the
	background worker) would bill less than the cashier showed, with no one to tell."""
	if doc.get("is_return") or not cint(doc.get("update_stock")):
		return
	if (
		doc.get("_action") == "submit"
		and not cint(doc.get("custom_is_created_from_klik"))
		and not _has_money(doc)
		and doc.get("pos_profile")
		and cint(frappe.db.get_value("POS Profile", doc.pos_profile, PROFILE_FLAG))
	):
		changes = split_invoice_rows(doc)
		if changes:
			_announce(changes)
	_allow_los_zero_rows(doc)


def _has_money(doc):
	"""Cash, a payment row, loyalty points or an advance is on the invoice. Payment rows are summed
	because paid_amount is only recomputed in validate, after this hook."""
	return any(
		flt(amount) > 0
		for amount in (
			doc.get("paid_amount"),
			sum(flt(row.amount) for row in doc.get("payments") or []),
			doc.get("loyalty_amount"),
			doc.get("total_advance"),
		)
	)


def _allow_los_zero_rows(doc):
	"""ERPNext refuses qty-0 lines. One that records Loss of Sale is meant to be there - and has
	to be allowed on every save, as a background submit reloads the invoice."""
	zero = [row for row in doc.items if not flt(row.qty)]
	if zero and all(flt(row.get(LOS_FIELD)) > 0 for row in zero):
		doc.flags.allow_zero_qty = True


def _announce(changes):
	rows = "".join(
		"<tr><td>{0}</td><td>{1}</td><td>{2} → {3}</td><td>{4}</td></tr>".format(
			change["idx"], frappe.bold(frappe.utils.escape_html(change["item_code"])), flt(change["from_qty"]), flt(change["qty"]), flt(change["los_qty"])
		)
		for change in changes
	)
	frappe.msgprint(
		"<table class='table table-bordered'><tr><th>{0}</th><th>{1}</th><th>{2}</th><th>{3}</th></tr>{4}</table>".format(
			_("Row"), _("Item"), _("Qty"), _("Loss of Sale"), rows
		),
		title=_("Sold what is in stock"),
		indicator="orange",
	)
