"""Quick entry: "item, qty, rate" lines typed into the POS, each item matched by its code.

The cashier types part of a code; the till finds the item. An exact item code wins (so
"twist300" is not stopped by "twist3000"); otherwise the one item whose code contains the
text, then the one item whose name contains it. Several matches fail the line, naming them:
a guess would put the wrong item on a sale. Only items this till sells can match - the
same scope as its product list - and the matched item comes back exactly as the product
list would hand it to the cart.
"""

import frappe
from frappe import _

from klik_pos.klik_pos.utils import get_current_pos_profile

from ..sql_builder import apply_sql_permissions
from .item_listing import get_items

MAX_LINES = 200
# Candidates named back for a line that matched several items.
CANDIDATES_SHOWN = 5


def _like(text):
	escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"


def _candidates(condition, value, allowed_groups):
	sql = f"""
		SELECT i.name
		FROM `tabItem` i
		WHERE i.disabled = 0
			AND IFNULL(i.is_sales_item, 1) = 1
			AND {condition}
			{"AND i.item_group IN %(groups)s" if allowed_groups else ""}
		ORDER BY i.name
		LIMIT {CANDIDATES_SHOWN + 1}
	"""
	return frappe.db.sql_list(
		apply_sql_permissions(sql), {"value": value, "groups": tuple(allowed_groups)}
	)


def _cart_item(code, customer, price_list, warehouse):
	"""The item as this till's product list offers it, or None when the list would not (out
	of stock on a till that hides those, a service item on a till without them)."""
	listing = get_items(limit=50, search=code, customer=customer, price_list=price_list, warehouse=warehouse)
	return next((item for item in listing.get("items") or [] if str(item.get("id")).lower() == code.lower()), None)


def _match(query, allowed_groups, customer, price_list, warehouse):
	result = {"query": query, "status": "none", "item": None, "candidates": []}
	for condition, value in (
		("i.name = %(value)s", query),
		("i.name LIKE %(value)s", _like(query)),
		("i.item_name LIKE %(value)s", _like(query)),
	):
		codes = _candidates(condition, value, allowed_groups)
		if not codes:
			continue
		if len(codes) > 1:
			result.update(status="many", candidates=codes[:CANDIDATES_SHOWN])
			return result
		code = codes[0]
		result["candidates"] = [code]
		if frappe.db.get_value("Item", code, "has_variants"):
			result["status"] = "template"
			return result
		item = _cart_item(code, customer, price_list, warehouse)
		result.update(status="ok" if item else "unavailable", item=item)
		return result
	return result


@frappe.whitelist(methods=["POST"])
def match_items(queries, customer=None, price_list=None, warehouse=None):
	"""One answer per query, in the order asked: {query, status, item, candidates}.

	status: ok (item is cart-ready), many (candidates lists them), none, template (an item
	with variants - the variant's code is needed), unavailable (the till does not offer it).
	"""
	queries = frappe.parse_json(queries) if isinstance(queries, str) else queries
	if not isinstance(queries, list):
		frappe.throw(_("Send the lines as a list."))
	if len(queries) > MAX_LINES:
		frappe.throw(_("Enter at most {0} lines at a time.").format(MAX_LINES))

	till = get_current_pos_profile()
	allowed_groups = [row.item_group for row in (getattr(till, "item_groups", None) or []) if row.item_group]

	answers = {}
	results = []
	for raw in queries:
		query = str(raw or "").strip()
		if query not in answers:
			answers[query] = (
				_match(query, allowed_groups, customer, price_list, warehouse)
				if query
				else {"query": query, "status": "none", "item": None, "candidates": []}
			)
		results.append(dict(answers[query]))
	return results
