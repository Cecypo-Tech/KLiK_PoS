"""Quick entry: an order pasted into the POS, in whatever shape the customer sent it.

Each line names an item - by its code, a barcode or the supplier's part number, often more than
one of them ("51360-TMJ-T01-B ASIMCO KY14094 4") - and maybe a quantity ("5pcs", "x5", a lone
number) and a rate ("@220"). Every line is matched in one request: exact matches first, in a
fixed number of queries; then, for a line nothing named exactly, the one item whose code or name
holds the text. A line that names several items, or none, is sent back for the cashier to settle:
a guess would put the wrong item on a sale. Only items this till sells can match, and a matched
item comes back as the product list would hand it to the cart, tax details included.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt

from klik_pos.klik_pos.utils import get_current_pos_profile

from ..sql_builder import apply_sql_permissions
from .item_listing import get_items
from .item_tax_details import get_item_tax_details

# A customer's order, not a stock import.
MAX_LINES = 500
# Candidates named back for a line that matched several items.
CANDIDATES_SHOWN = 5


_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_IS_NUMBER = re.compile(rf"^{_NUMBER}$")
# A quantity the line marks as one: 5pcs, 5pc, 5pce, 5x, x5, qty5, qty:5.
_MARKED_QTY = re.compile(rf"^(?:x({_NUMBER})|({_NUMBER})(?:pcs?|pce|x)|qty:?({_NUMBER}))$", re.I)
# "5 pcs", "x 5", "qty 5", "@ 220" written apart: joined so each is one token.
_JOINS = (
	(re.compile(rf"(?<![\w.])({_NUMBER})\s+(pcs?|pce)\b", re.I), r"\1\2"),
	(re.compile(r"\b(qty:?|x)\s+(?=[\d.])", re.I), r"\1"),
	(re.compile(r"@\s+"), "@"),
)
_RATE_RULE = "Rate must be more than 0 (leave it out for the till's price)"


def parse_line(text):
	"""What a line says before any item is looked up.

	A marked quantity ("5pcs", "x5") is the quantity wherever it sits. Bare numbers wait: one of
	them may be the item's own part number, so the quantity is settled once the item is known.
	"item, qty[, rate]" lines are read as they always were.
	"""
	text = str(text or "").strip()
	parsed = {
		"text": text,
		"item_tokens": [],
		"numbers": [],
		"qty": None,
		"qty_ambiguous": False,
		"rate": None,
		"error": None,
	}
	parts = [part.strip() for part in text.split(",")]
	if 2 <= len(parts) <= 3 and parts[0] and _IS_NUMBER.match(parts[1]):
		parsed["item_tokens"] = [parts[0]]
		parsed["qty"] = float(parts[1])
		if len(parts) == 3 and parts[2]:
			if not _IS_NUMBER.match(parts[2]):
				parsed["error"] = _("Rate must be a number")
				return parsed
			parsed["rate"] = float(parts[2])
	else:
		for pattern, joined in _JOINS:
			text = pattern.sub(joined, text)
		for token in re.split(r"[\s,]+", text):
			marked = _MARKED_QTY.match(token)
			if marked:
				parsed["qty_ambiguous"] = parsed["qty"] is not None
				parsed["qty"] = float(next(group for group in marked.groups() if group))
			elif token.startswith("@") and _IS_NUMBER.match(token[1:]):
				parsed["rate"] = float(token[1:])
			elif _IS_NUMBER.match(token):
				parsed["numbers"].append(token)
			elif re.search(r"[A-Za-z]", token) or (re.search(r"\d", token) and "-" in token):
				parsed["item_tokens"].append(token)
	if parsed["qty"] is not None and parsed["qty"] <= 0:
		parsed["error"] = _("Quantity must be more than 0")
	elif parsed["rate"] is not None and parsed["rate"] <= 0:
		parsed["error"] = _(_RATE_RULE)
	return parsed


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


def _scope(allowed_groups):
	return "i.disabled = 0 AND IFNULL(i.is_sales_item, 1) = 1" + (
		" AND i.item_group IN %(groups)s" if allowed_groups else ""
	)


def _exact_hits(keys, allowed_groups):
	"""{key, lowercased: {item codes}} for every key that is an item's code, barcode or supplier
	part number. Three queries, however many lines. A key that is an item's own code means that
	item, even where another item lists it as a barcode or the supplier's part number."""
	hits = {}
	if not keys:
		return hits
	params = {"keys": tuple(keys), "groups": tuple(allowed_groups)}
	codes_named = set()
	for index, sql in enumerate((
		"SELECT i.name AS code, i.name AS hit FROM `tabItem` i WHERE i.name IN %(keys)s",
		"SELECT i.name AS code, b.barcode AS hit FROM `tabItem` i "
		"JOIN `tabItem Barcode` b ON b.parent = i.name WHERE b.barcode IN %(keys)s",
		"SELECT i.name AS code, s.supplier_part_no AS hit FROM `tabItem` i "
		"JOIN `tabItem Supplier` s ON s.parent = i.name WHERE s.supplier_part_no IN %(keys)s",
	)):
		rows = frappe.db.sql(apply_sql_permissions(f"{sql} AND {_scope(allowed_groups)}"), params, as_dict=True)
		for row in rows:
			if row.hit.lower() not in codes_named:
				hits.setdefault(row.hit.lower(), set()).add(row.code)
		if index == 0:
			codes_named = set(hits)
	return hits


def _substring_match(token, allowed_groups):
	"""The search for a line nothing named exactly: item codes, then item names, holding the token."""
	for condition in ("i.name LIKE %(value)s", "i.item_name LIKE %(value)s"):
		codes = _candidates(condition, _like(token), allowed_groups)
		if codes:
			return codes
	return []


def _answer(parsed, hits, allowed_groups):
	"""The line's item codes, how they were found, and its quantity.

	Where the tokens that hit agree on one item ("54560-1HJ0A KY10004": a part number two brands
	share, and one brand's code), that is the item; where they share none, they conflict."""
	named = [hits[t.lower()] for t in parsed["item_tokens"] if hits.get(t.lower())]
	codes = set.intersection(*named) if named else set()
	if not codes and named:
		codes = set().union(*named)
	numbers = list(parsed["numbers"])
	how = "exact"
	if not codes:
		# A bare number may be the part number (a numeric supplier part); then it is not the qty.
		for number in parsed["numbers"]:
			if hits.get(number.lower()):
				codes |= hits[number.lower()]
				numbers.remove(number)
	if not codes:
		how = "substring"
		for token in parsed["item_tokens"]:
			codes = set(_substring_match(token, allowed_groups))
			if codes:
				break
	if parsed["qty"] is not None:
		qty, ambiguous = parsed["qty"], parsed["qty_ambiguous"]
	elif numbers:
		qty, ambiguous = float(numbers[-1]), len(numbers) > 1
	else:
		qty, ambiguous = 1.0, False
	return sorted(codes), how, qty, ambiguous


@frappe.whitelist(methods=["POST"])
def resolve_lines(lines, customer=None, price_list=None, warehouse=None):
	"""One answer per line, in the order sent: {text, status, qty, qty_ambiguous, rate, item,
	candidates, reason}.

	status: ok (item is cart-ready, tax details included), many (a partial match found several),
	conflict (the line names different items exactly), none, template (an item with variants),
	unavailable (the till's product list does not offer it), invalid (a value the line cannot
	have; reason says which).
	"""
	lines = frappe.parse_json(lines) if isinstance(lines, str) else lines
	if not isinstance(lines, list):
		frappe.throw(_("Send the lines as a list."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("Enter at most {0} lines at a time.").format(MAX_LINES))

	till = get_current_pos_profile()
	allowed_groups = [row.item_group for row in (getattr(till, "item_groups", None) or []) if row.item_group]

	parsed = [parse_line(text) for text in lines]
	keys = sorted({key for p in parsed for key in p["item_tokens"] + p["numbers"]})
	hits = _exact_hits(keys, allowed_groups)

	answers = []
	for p in parsed:
		codes, how, qty, ambiguous = _answer(p, hits, allowed_groups)
		answer = {
			"text": p["text"],
			"status": "none",
			"qty": qty,
			"qty_ambiguous": ambiguous,
			"rate": p["rate"],
			"item": None,
			"candidates": codes[:CANDIDATES_SHOWN],
			"reason": None,
		}
		if p["error"] or qty <= 0:
			answer.update(status="invalid", reason=p["error"] or _("Quantity must be more than 0"))
		elif len(codes) > 1:
			answer["status"] = "conflict" if how == "exact" else "many"
		elif codes:
			answer["status"] = "ok"
		answers.append(answer)

	single = sorted({a["candidates"][0] for a in answers if a["status"] == "ok"})
	templates = (
		set(frappe.get_all("Item", filters={"name": ["in", single], "has_variants": 1}, pluck="name"))
		if single
		else set()
	)
	offered = {}
	wanted = [code for code in single if code not in templates]
	if wanted:
		listing = get_items(
			limit=len(wanted), customer=customer, price_list=price_list, warehouse=warehouse, item_codes=wanted
		)
		offered = {str(item.get("id")).lower(): item for item in listing.get("items") or []}
	# The tax lookup the cart used to make per line, made here once per item.
	for item in offered.values():
		tax = get_item_tax_details(item["id"], customer=customer, qty=1, uom=item.get("uom"))
		tax_info = tax.get("tax_info") or {}
		item.update(
			item_tax_template=tax.get("item_tax_template") or "",
			item_tax_rate=tax.get("item_tax_rate") or {},
			tax_templates=tax_info.get("tax_templates") or [],
			total_tax_rate=flt(tax_info.get("total_tax_rate")),
		)

	all_candidates = sorted({c for a in answers for c in a["candidates"]})
	names = (
		dict(frappe.get_all("Item", filters={"name": ["in", all_candidates]}, fields=["name", "item_name"], as_list=True))
		if all_candidates
		else {}
	)
	for answer in answers:
		code = answer["candidates"][0] if answer["candidates"] else None
		if answer["status"] == "ok":
			answer["candidates"] = []
			if code in templates:
				answer.update(
					status="template", reason=_("{0} has variants: enter the variant's code").format(code), candidates=[code]
				)
			else:
				answer["item"] = offered.get(code.lower())
				if not answer["item"]:
					answer.update(
						status="unavailable", reason=_("{0} is not available on this till").format(code), candidates=[code]
					)
		elif answer["status"] == "none":
			answer["reason"] = _('No item matches "{0}"').format(answer["text"])
		elif answer["status"] == "many":
			answer["reason"] = _("Several items match: pick one")
		elif answer["status"] == "conflict":
			answer["reason"] = _("The line names different items: pick one")
		answer["candidates"] = [{"code": c, "name": names.get(c, c)} for c in answer["candidates"]]
	return answers
