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

# A typed order, not a stock import: each line costs a cart add with its own tax lookup.
MAX_LINES = 50
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


def _resolve(query, allowed_groups):
	"""The one item code `query` means, or why there is none."""
	result = {"query": query, "status": "none", "item": None, "candidates": []}
	if not query:
		return result
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
		result.update(status="ok", candidates=codes)
		if frappe.db.get_value("Item", codes[0], "has_variants"):
			result["status"] = "template"
		return result
	return result


@frappe.whitelist(methods=["POST"])
def match_items(queries, customer=None, price_list=None, warehouse=None):
	"""One answer per query, in the order asked: {query, status, item, candidates}.

	status: ok (item is cart-ready), many (candidates lists them), none, template (an item
	with variants - the variant's code is needed), unavailable (the till's product list does
	not offer it: out of stock on a till that hides those, a service item on one without).
	"""
	queries = frappe.parse_json(queries) if isinstance(queries, str) else queries
	if not isinstance(queries, list):
		frappe.throw(_("Send the lines as a list."))
	if len(queries) > MAX_LINES:
		frappe.throw(_("Enter at most {0} lines at a time.").format(MAX_LINES))

	till = get_current_pos_profile()
	allowed_groups = [row.item_group for row in (getattr(till, "item_groups", None) or []) if row.item_group]

	answers = {}
	for raw in queries:
		query = str(raw or "").strip()
		if query not in answers:
			answers[query] = _resolve(query, allowed_groups)

	# The matched items as the product list offers them, in one listing call.
	codes = sorted({a["candidates"][0] for a in answers.values() if a["status"] == "ok"})
	offered = {}
	if codes:
		listing = get_items(
			limit=len(codes), customer=customer, price_list=price_list, warehouse=warehouse, item_codes=codes
		)
		offered = {str(item.get("id")).lower(): item for item in listing.get("items") or []}
	for answer in answers.values():
		if answer["status"] == "ok":
			answer["item"] = offered.get(answer["candidates"][0].lower())
			if not answer["item"]:
				answer["status"] = "unavailable"

	return [dict(answers[str(raw or "").strip()]) for raw in queries]
