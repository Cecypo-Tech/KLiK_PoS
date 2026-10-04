# Loss of Sale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a line asks for more than the warehouse holds, sell what is in stock and record the shortfall on the invoice line as a read-only `LoS Qty`, instead of refusing the sale.

**Architecture:** One pure allocation function (`split_lines`) does the split. Two adapters use it. `split_cart_items` shortens the till's parsed cart lines before the invoice is built. It has to run before the build because the builder checks batch stock against the cart quantities. `split_invoice_rows` shortens a Sales Invoice's own rows, and a `before_validate` doc_event calls it on submit for unpaid invoices whose POS Profile has LoS on. The SPA mirrors the rule in a pure TS helper, so the cart splits as the cashier types. The server's checkout preview is the authority, and it sends corrections back before payment.

**Tech Stack:** Frappe v16 / ERPNext v16 (Python, `create_custom_fields`, doc_events), React + zustand SPA (TypeScript, vitest).

**Spec:** `artifacts/superpowers/2026-10-04-loss-of-sale-design.md`

## Global Constraints

- Branch `feat/loss-of-sale`, worktree `/home/kushal/frappe-bench/apps/klik_pos-wt-los`. The main checkout `apps/klik_pos` belongs to another session: never edit it, switch its branch or build in it.
- Field names, exactly: POS Profile `custom_enable_loss_of_sale` (Check). Sales Invoice Item `custom_los_qty` (Float, read_only, in_list_view, no_copy, print_hide, insert_after `qty`).
- Requested = qty + los_qty. Every split re-derives the line from that, so re-running it is a no-op.
- LoS applies only to: stock items, `allow_negative_stock = 0`, `has_serial_no = 0`, lines with no serial/batch chosen, invoices with `update_stock = 1` that are not returns, and POS Profiles with the flag on. Everything else keeps today's behaviour.
- A paid invoice is never shortened. Payment includes cash, loyalty and customer credit.
- If no line has qty > 0 after a split, refuse with "Nothing on this sale is in stock."
- Commit messages: no `Co-Authored-By` lines. End each with `Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7`.
- Python files in `klik_pos/api/` and `klik_pos/overrides/` indent with tabs. `klik_pos/setup/pos_profile_fields.py` and `klik_pos/api/sales_order.py` indent with 4 spaces. Match the file.

## Review Focus

1. **A paid till sale with a qty-0 LoS line.** It must save, submit (including a background submit that reloads the document) and post no stock for that line. The `allow_zero_qty` flag is set on every validate, not only at the split. Pinned in Task 4: `test_a_paid_sale_records_the_loss_on_its_line`.
2. **Stock drops between the preview and a paid submit.** The sale is refused as today and nothing is shortened. Pinned in Task 4: `test_a_paid_oversell_is_still_refused`.
3. **Two lines of the same item.** They share one stock pool, and earlier lines fill first. Pinned in Task 2: `test_two_lines_share_the_stock_in_order`.
4. **A whole-number UOM with a conversion factor** (a Box of 6, with 10 units on hand). One box is sold and the rest is LoS; the box is never fractional. Pinned in Task 2: `test_whole_number_uom_floors_to_whole_units`.
5. **A till with LoS off receiving a stale `los_qty`** (a cart split while the flag was on). Nothing is recorded as LoS. Pinned in Task 2: `test_with_loss_of_sale_off_nothing_changes`.

## Test harness (set up once, before Task 1)

`bench run-tests` imports `klik_pos` from the main checkout, not this worktree. Run Python tests with this runner, which puts the worktree first on `sys.path`.

- [ ] Create `/tmp/claude-1000/-home-kushal-frappe-bench-apps-klik-pos/26312704-6758-4d05-b165-51a5678c6049/scratchpad/run_los_test.py`:

```python
import sys
import unittest

sys.path.insert(0, "/home/kushal/frappe-bench/apps/klik_pos-wt-los")
import frappe

frappe.init(site="dev.localhost")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_test = True
import klik_pos

assert "klik_pos-wt-los" in klik_pos.__file__, klik_pos.__file__
names = sys.argv[1:]
suite = unittest.TestSuite(
	unittest.defaultTestLoader.loadTestsFromName(f"klik_pos.tests.{name}") for name in names
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
frappe.destroy()
sys.exit(not result.wasSuccessful())
```

Run with: `cd ~/frappe-bench/sites && ../env/bin/python <runner> <module>[.<Class>.<test>] ...`. In the task steps below, this is `RUN <module>`.

- [ ] Before trusting a red run, check that no other session is testing the site: `ps -eo cmd | grep 'run-tests' | grep -v grep`. Two sessions collide with `TimestampMismatchError` on System Settings. Rerun once the other run is gone.
- [ ] SPA tooling: `ln -sfn /home/kushal/frappe-bench/apps/klik_pos/klik_spa/node_modules /home/kushal/frappe-bench/apps/klik_pos-wt-los/klik_spa/node_modules && ln -sfn /home/kushal/frappe-bench/apps/klik_pos/node_modules /home/kushal/frappe-bench/apps/klik_pos-wt-los/node_modules`. Both are gitignored.

---

### Task 1: Fields and the shared stock-availability helper

**Files:**
- Modify: `klik_pos/setup/pos_profile_fields.py`: append to `POS_PROFILE_FEATURE_FIELDS`; add `LOS_QTY_FIELD`, `install_los_qty_field`, `ensure_los_qty_field`; call it from `ensure_pos_profile_feature_fields`
- Modify: `klik_pos/api/sales_invoice.py`: add `get_available_stock_map` above `_validate_reserved_stock_for_items` and make that function use it
- Test: `klik_pos/tests/test_loss_of_sale.py` (new; later tasks add to it)

**Interfaces:**
- Produces: `install_los_qty_field() -> bool` and `ensure_los_qty_field() -> None` (in `klik_pos.setup.pos_profile_fields`). `get_available_stock_map(keys, exclude_invoice=None) -> dict[(item_code, warehouse), frappe._dict(actual_qty, reserved_qty, available_qty)]`, which returns one entry per key, including keys with no Bin (actual 0).

- [ ] **Step 1: Write the failing tests.** Create `klik_pos/tests/test_loss_of_sale.py`:

```python
"""Loss of Sale: when a line asks for more than the warehouse holds, sell what is there and
record the rest on the line as LoS Qty."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from klik_pos.setup.pos_profile_fields import install_los_qty_field, install_pos_profile_feature_fields

ITEM_GROUP = "TEST-LOS-GROUP"
STOCKED = "TEST-LOS-STOCKED"  # 10 in the till's warehouse
EMPTY = "TEST-LOS-EMPTY"  # none anywhere
CUSTOMER = "TEST-LOS-CUSTOMER"


def _profile():
	"""The till the session sells from when a shift is open, else any enabled POS Profile."""
	from klik_pos.api.sales_invoice import get_current_pos_opening_entry
	from klik_pos.klik_pos.utils import get_current_pos_profile

	if get_current_pos_opening_entry():
		try:
			return get_current_pos_profile()
		except Exception:
			pass
	name = frappe.db.get_value("POS Profile", {"disabled": 0, "warehouse": ["is", "set"]}, "name")
	return frappe.get_doc("POS Profile", name) if name else None


def _make_item(code):
	if frappe.db.exists("Item", code):
		return
	item = frappe.new_doc("Item")
	item.item_code = code
	item.item_name = code
	item.item_group = ITEM_GROUP
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.is_sales_item = 1
	item.insert(ignore_permissions=True)


class TestLossOfSale(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		install_pos_profile_feature_fields()
		install_los_qty_field()
		frappe.db.commit()
		cls.ready = False
		cls.profile = _profile()
		if not cls.profile:
			return
		cls.warehouse = cls.profile.warehouse
		cls.company = cls.profile.company

		if not frappe.db.exists("Item Group", ITEM_GROUP):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups", "is_group": 0}
			).insert(ignore_permissions=True)
		_make_item(STOCKED)
		_make_item(EMPTY)
		if not frappe.db.exists("Customer", CUSTOMER):
			customer = frappe.new_doc("Customer")
			customer.customer_name = CUSTOMER
			customer.customer_type = "Individual"
			customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
			customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
			customer.insert(ignore_permissions=True)
		cls.customer = CUSTOMER

		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		cls.stock_entry = make_stock_entry(
			item_code=STOCKED, target=cls.warehouse, qty=10, basic_rate=10, company=cls.company
		)
		frappe.db.commit()
		cls.ready = True

	@classmethod
	def tearDownClass(cls):
		if getattr(cls, "ready", False):
			for name in frappe.get_all(
				"Sales Invoice Item", filters={"item_code": ["in", [STOCKED, EMPTY]]}, pluck="parent", distinct=True
			):
				cls._drop_invoice(name)
			entry = frappe.get_doc("Stock Entry", cls.stock_entry.name)
			if entry.docstatus == 1:
				entry.flags.ignore_permissions = True
				entry.cancel()
			frappe.delete_doc("Stock Entry", entry.name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Bin", filters={"item_code": ["in", [STOCKED, EMPTY]]}, pluck="name"):
				frappe.delete_doc("Bin", name, force=True, ignore_permissions=True)
			for code in (STOCKED, EMPTY):
				if frappe.db.exists("Item", code):
					frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
			for doctype, name in (("Item Group", ITEM_GROUP), ("Customer", CUSTOMER)):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	@staticmethod
	def _drop_invoice(name):
		if not name or not frappe.db.exists("Sales Invoice", name):
			return
		invoice = frappe.get_doc("Sales Invoice", name)
		if invoice.docstatus == 1:
			invoice.flags.ignore_permissions = True
			invoice.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		if not getattr(self.__class__, "ready", False):
			self.skipTest("no enabled POS Profile with a warehouse on this site")
		frappe.set_user("Administrator")

	# Task 1

	def test_the_fields_exist(self):
		field = frappe.get_meta("Sales Invoice Item").get_field("custom_los_qty")
		self.assertIsNotNone(field)
		self.assertEqual((field.fieldtype, field.read_only, field.in_list_view, field.no_copy), ("Float", 1, 1, 1))
		self.assertIsNotNone(frappe.get_meta("POS Profile").get_field("custom_enable_loss_of_sale"))
		self.assertFalse(install_los_qty_field(), "a second install must be a no-op")

	def test_available_stock_is_net_of_reservations(self):
		from klik_pos.api.sales_invoice import get_available_stock_map

		keys = {(STOCKED, self.warehouse), (EMPTY, self.warehouse)}
		stock = get_available_stock_map(keys)
		self.assertEqual(stock[(STOCKED, self.warehouse)].available_qty, 10)
		self.assertEqual(stock[(EMPTY, self.warehouse)].available_qty, 0)

		with patch(
			"klik_pos.api.sales_invoice.get_reserved_stock_map",
			return_value={(STOCKED, self.warehouse): 4},
		):
			row = get_available_stock_map(keys)[(STOCKED, self.warehouse)]
		self.assertEqual((row.actual_qty, row.reserved_qty, row.available_qty), (10, 4, 6))
```

- [ ] **Step 2: Run, expect failure.** `RUN test_loss_of_sale`. Expected: ImportError for `install_los_qty_field`.

- [ ] **Step 3: Add the fields.** In `klik_pos/setup/pos_profile_fields.py`, append this entry as the last element of `POS_PROFILE_FEATURE_FIELDS`, just before its closing `]`:

```python
    {
        "fieldname": "custom_enable_loss_of_sale",
        "label": "Record Loss of Sale",
        "fieldtype": "Check",
        "insert_after": "custom_use_item_code_as_display_name",
        "description": (
            "When a cashier asks for more than is in stock, sell what is in stock and record "
            "the rest on the invoice line as LoS Qty (Loss of Sale) instead of refusing the line."
        ),
        "default": "0",
        "module": "KLiK PoS",
    },
```

Above `def ensure_pos_profile_feature_fields():`, add:

```python
LOS_QTY_FIELD = {
    "fieldname": "custom_los_qty",
    "label": "LoS Qty",
    "fieldtype": "Float",
    "insert_after": "qty",
    "read_only": 1,
    "in_list_view": 1,
    "columns": 1,
    "no_copy": 1,
    "print_hide": 1,
    "description": "Asked for but not in stock: recorded as Loss of Sale.",
    "module": "KLiK PoS",
}


def install_los_qty_field():
    """LoS Qty on Sales Invoice Item. Returns True when created."""
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice Item", "fieldname": LOS_QTY_FIELD["fieldname"]}):
        return False
    create_custom_fields({"Sales Invoice Item": [LOS_QTY_FIELD]}, update=True)
    return True


def ensure_los_qty_field():
    try:
        install_los_qty_field()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "klik_pos: LoS Qty field install failed")
```

At the end of `ensure_pos_profile_feature_fields`, after `ensure_sales_order_remarks()`, add `ensure_los_qty_field()`.

- [ ] **Step 4: Extract the availability helper.** In `klik_pos/api/sales_invoice.py`, add directly above `def _validate_reserved_stock_for_items`:

```python
def get_available_stock_map(keys, exclude_invoice=None):
	"""{(item_code, warehouse): actual_qty, reserved_qty, available_qty} for each key - available
	being net of Stock Reservation Entries, the figure both the oversell refusal and Loss of Sale
	measure against. A key with no Bin has none."""
	keys = set(keys)
	if not keys:
		return {}
	bins = frappe.get_all(
		"Bin",
		filters={
			"item_code": ["in", list({key[0] for key in keys})],
			"warehouse": ["in", list({key[1] for key in keys})],
		},
		fields=["item_code", "warehouse", "actual_qty"],
	)
	actual_map = {(row.item_code, row.warehouse): flt(row.actual_qty or 0) for row in bins}
	reserved_map = get_reserved_stock_map(
		item_codes=list({key[0] for key in keys}),
		exclude_invoice=exclude_invoice,
	)
	stock = {}
	for key in keys:
		actual_qty = flt(actual_map.get(key, 0))
		reserved_qty = flt(reserved_map.get(key, 0))
		stock[key] = frappe._dict(
			actual_qty=actual_qty, reserved_qty=reserved_qty, available_qty=flt(actual_qty - reserved_qty)
		)
	return stock
```

In `_validate_reserved_stock_for_items`, replace everything from `bins = frappe.get_all(` through the end of the `for key, required_qty in required_qty_map.items():` loop header's first three lines with this. The `if required_qty > available_qty + 1e-9:` block and the throw stay as they are.

```python
	stock = get_available_stock_map(required_qty_map.keys(), exclude_invoice=exclude_invoice)

	insufficient = []
	for key, required_qty in required_qty_map.items():
		actual_qty = stock[key].actual_qty
		reserved_qty = stock[key].reserved_qty
		available_qty = stock[key].available_qty
```

`item_codes` and `warehouses` in that function are now unused. Delete them along with the lines that fill them (`item_codes = set()`, `warehouses = set()`, `item_codes.add(...)`, `warehouses.add(...)`).

- [ ] **Step 5: Run, expect pass.** `RUN test_loss_of_sale test_checkout_stock_validation`. Expected: both OK. The second suite proves the refactor kept the refusal.

- [ ] **Step 6: Commit.**

```bash
cd /home/kushal/frappe-bench/apps/klik_pos-wt-los
git add klik_pos/setup/pos_profile_fields.py klik_pos/api/sales_invoice.py klik_pos/tests/test_loss_of_sale.py
git commit -m "feat(los): LoS Qty and Record Loss of Sale fields, shared stock availability

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 2: The split rule and the till-cart adapter

**Files:**
- Create: `klik_pos/overrides/loss_of_sale.py`
- Test: `klik_pos/tests/test_loss_of_sale_split.py` (new, pure, no DB)
- Test: `klik_pos/tests/test_loss_of_sale.py` (add the Task 2 tests)

**Interfaces:**
- Consumes: `get_available_stock_map` (Task 1).
- Produces, in `klik_pos.overrides.loss_of_sale`:
  - `LOS_FIELD = "custom_los_qty"` and `PROFILE_FLAG = "custom_enable_loss_of_sale"`
  - `split_lines(lines, available) -> list[tuple[float, float]]`. `lines` are dicts `{key, requested, factor, whole}`; `available` is `{key: stock_units}`.
  - `split_cart_items(items, pos_profile) -> list[dict]`. It mutates `items` (parse_invoice_data's dicts: `id`, `quantity`, `los_qty`, `uom`, `bundle_entries`) and returns `[{index, item_code, quantity, los_qty}]` for the changed lines.
  - `fold_los_into_quantity(items) -> items`
  - `_eligible_item_codes`, `_whole_number_uoms`, `_available`, `_refuse_if_nothing_sold` (used by Task 3)

- [ ] **Step 1: Write the failing pure tests.** Create `klik_pos/tests/test_loss_of_sale_split.py`:

```python
"""The Loss of Sale split rule, without a database."""

import unittest

from klik_pos.overrides.loss_of_sale import fold_los_into_quantity, split_lines

A = ("ITEM-A", "Stores")


def line(requested, factor=1, whole=False, key=A):
	return {"key": key, "requested": requested, "factor": factor, "whole": whole}


class TestSplitLines(unittest.TestCase):
	def test_partial_shortage_sells_what_is_there(self):
		self.assertEqual(split_lines([line(16)], {A: 10}), [(10, 6)])

	def test_enough_stock_changes_nothing(self):
		self.assertEqual(split_lines([line(4)], {A: 10}), [(4, 0)])

	def test_no_stock_keeps_a_zero_line(self):
		self.assertEqual(split_lines([line(6)], {}), [(0, 6)])

	def test_two_lines_share_the_stock_in_order(self):
		self.assertEqual(split_lines([line(7), line(7)], {A: 10}), [(7, 0), (3, 4)])

	def test_conversion_factor_counts_stock_units(self):
		# 2 boxes of 6 asked, 9 units held: 1.5 boxes in a UOM that allows fractions
		self.assertEqual(split_lines([line(2, factor=6)], {A: 9}), [(1.5, 0.5)])

	def test_whole_number_uom_floors_to_whole_units(self):
		# 2 boxes of 6 asked, 10 units held: one whole box sells
		self.assertEqual(split_lines([line(2, factor=6, whole=True)], {A: 10}), [(1, 1)])

	def test_negative_stock_counts_as_none(self):
		self.assertEqual(split_lines([line(3)], {A: -5}), [(0, 3)])

	def test_running_it_again_on_its_own_result_is_a_no_op(self):
		qty, los = split_lines([line(16)], {A: 10})[0]
		self.assertEqual(split_lines([line(qty + los)], {A: 10}), [(qty, los)])


class TestFold(unittest.TestCase):
	def test_a_held_order_keeps_what_was_asked_for(self):
		items = [{"id": "X", "quantity": 10, "los_qty": 6}, {"id": "Y", "quantity": 0, "los_qty": 3}]
		self.assertEqual(
			[(i["quantity"], i["los_qty"]) for i in fold_los_into_quantity(items)], [(16, 0), (3, 0)]
		)
```

- [ ] **Step 2: Add the failing DB tests.** Append to `TestLossOfSale` in `klik_pos/tests/test_loss_of_sale.py`. Also add `from klik_pos.tests.pos_fixtures import pos_profile_settings` to the module imports.

```python
	# Task 2

	def _cart(self, *lines):
		return [
			{"id": code, "quantity": qty, "los_qty": los, "uom": "Nos", "bundle_entries": []}
			for code, qty, los in lines
		]

	def _split(self, cart, enabled=1):
		from klik_pos.overrides.loss_of_sale import split_cart_items

		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=enabled):
			return split_cart_items(cart, frappe.get_doc("POS Profile", self.profile.name))

	def test_the_till_sells_what_is_in_stock(self):
		cart = self._cart((STOCKED, 16, 0))
		changes = self._split(cart)
		self.assertEqual((cart[0]["quantity"], cart[0]["los_qty"]), (10, 6))
		self.assertEqual(changes, [{"index": 0, "item_code": STOCKED, "quantity": 10, "los_qty": 6}])

	def test_with_loss_of_sale_off_nothing_changes(self):
		cart = self._cart((STOCKED, 16, 0), (STOCKED, 2, 3))
		self.assertEqual(self._split(cart, enabled=0), [])
		self.assertEqual([(i["quantity"], i["los_qty"]) for i in cart], [(16, 0), (2, 0)])

	def test_an_item_with_no_stock_stays_as_a_zero_line(self):
		cart = self._cart((STOCKED, 4, 0), (EMPTY, 6, 0))
		self._split(cart)
		self.assertEqual([(i["quantity"], i["los_qty"]) for i in cart], [(4, 0), (0, 6)])

	def test_a_sale_with_nothing_in_stock_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing on this sale is in stock"):
			self._split(self._cart((EMPTY, 6, 0)))

	def test_reserved_stock_is_not_offered(self):
		cart = self._cart((STOCKED, 16, 0))
		with patch(
			"klik_pos.api.sales_invoice.get_reserved_stock_map",
			return_value={(STOCKED, self.warehouse): 4},
		):
			self._split(cart)
		self.assertEqual((cart[0]["quantity"], cart[0]["los_qty"]), (6, 10))

	def test_splitting_twice_changes_nothing_the_second_time(self):
		cart = self._cart((STOCKED, 16, 0))
		self._split(cart)
		self.assertEqual(self._split(cart), [])
```

- [ ] **Step 3: Run, expect failure.** `RUN test_loss_of_sale_split test_loss_of_sale`. Expected: `ModuleNotFoundError: klik_pos.overrides.loss_of_sale`.

- [ ] **Step 4: Implement.** Create `klik_pos/overrides/loss_of_sale.py`:

```python
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
```

- [ ] **Step 5: Run, expect pass.** `RUN test_loss_of_sale_split test_loss_of_sale`. Expected: OK.

- [ ] **Step 6: Commit.**

```bash
git add klik_pos/overrides/loss_of_sale.py klik_pos/tests/test_loss_of_sale_split.py klik_pos/tests/test_loss_of_sale.py
git commit -m "feat(los): split a cart against the stock there is

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 3: Desk submit shortens an unpaid invoice

**Files:**
- Modify: `klik_pos/overrides/loss_of_sale.py` (add `split_invoice_rows`, `before_validate`, `_allow_los_zero_rows`, `_announce`)
- Modify: `klik_pos/hooks.py`: in `doc_events["Sales Invoice"]`, add `"before_validate": "klik_pos.overrides.loss_of_sale.before_validate",`
- Test: `klik_pos/tests/test_loss_of_sale.py` (add the Task 3 tests)

**Interfaces:**
- Consumes: `split_lines`, `_eligible_item_codes`, `_whole_number_uoms`, `_available`, `_refuse_if_nothing_sold`, `LOS_FIELD`, `PROFILE_FLAG` (Task 2).
- Produces: `split_invoice_rows(doc) -> list[{idx, item_code, from_qty, qty, los_qty}]` and `before_validate(doc, method=None)` (the doc_event).

- [ ] **Step 1: Write the failing tests.** Append to `TestLossOfSale`:

```python
	# Task 3

	def _desk_invoice(self, *rows):
		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = self.customer
		invoice.company = self.company
		invoice.pos_profile = self.profile.name
		invoice.update_stock = 1
		for code, qty in rows:
			invoice.append("items", {"item_code": code, "qty": qty, "rate": 100, "warehouse": self.warehouse})
		invoice.insert(ignore_permissions=True)
		self.addCleanup(self._drop_invoice, invoice.name)
		return invoice

	def _ledger(self, invoice):
		return {
			row.item_code: row.actual_qty
			for row in frappe.get_all(
				"Stock Ledger Entry",
				filters={"voucher_no": invoice.name, "is_cancelled": 0},
				fields=["item_code", "actual_qty"],
			)
		}

	def test_desk_submit_sells_what_is_in_stock(self):
		invoice = self._desk_invoice((STOCKED, 16))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			invoice.submit()
		self.assertEqual((invoice.items[0].qty, invoice.items[0].custom_los_qty), (10, 6))
		self.assertEqual(self._ledger(invoice), {STOCKED: -10})

	def test_desk_zero_stock_line_is_kept_without_a_ledger_entry(self):
		invoice = self._desk_invoice((STOCKED, 4), (EMPTY, 6))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			invoice.submit()
		self.assertEqual([(row.qty, row.custom_los_qty) for row in invoice.items], [(4, 0), (0, 6)])
		self.assertEqual(self._ledger(invoice), {STOCKED: -4})

	def test_desk_with_loss_of_sale_off_still_refuses(self):
		invoice = self._desk_invoice((STOCKED, 16))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=0):
			with self.assertRaises(frappe.ValidationError):
				invoice.submit()

	def test_desk_sale_with_nothing_in_stock_is_refused(self):
		invoice = self._desk_invoice((EMPTY, 6))
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			with self.assertRaisesRegex(frappe.ValidationError, "Nothing on this sale is in stock"):
				invoice.submit()

	def test_a_paid_invoice_is_never_shortened(self):
		from klik_pos.overrides.loss_of_sale import before_validate

		invoice = frappe.new_doc("Sales Invoice")
		invoice.update({"customer": self.customer, "company": self.company, "pos_profile": self.profile.name})
		invoice.update_stock = 1
		invoice.paid_amount = 50
		invoice.append("items", {"item_code": STOCKED, "qty": 16, "rate": 100, "warehouse": self.warehouse})
		invoice._action = "submit"
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			before_validate(invoice)
		self.assertEqual((invoice.items[0].qty, invoice.items[0].get("custom_los_qty") or 0), (16, 0))
```

- [ ] **Step 2: Run, expect failure.** `RUN test_loss_of_sale`. Expected: `ImportError: cannot import name 'before_validate'`, and the Desk submit tests fail on ERPNext's "units of Item … needed" error.

- [ ] **Step 3: Implement.** Append to `klik_pos/overrides/loss_of_sale.py`:

```python
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
	A paid invoice is left alone: shortening it would leave money unaccounted for."""
	if doc.get("is_return") or not cint(doc.get("update_stock")):
		return
	if (
		doc.get("_action") == "submit"
		and not flt(doc.get("paid_amount"))
		and doc.get("pos_profile")
		and cint(frappe.db.get_value("POS Profile", doc.pos_profile, PROFILE_FLAG))
	):
		changes = split_invoice_rows(doc)
		if changes:
			_announce(changes)
	_allow_los_zero_rows(doc)


def _allow_los_zero_rows(doc):
	"""ERPNext refuses qty-0 lines. One that records Loss of Sale is meant to be there - and has
	to be allowed on every save, as a background submit reloads the invoice."""
	zero = [row for row in doc.items if not flt(row.qty)]
	if zero and all(flt(row.get(LOS_FIELD)) > 0 for row in zero):
		doc.flags.allow_zero_qty = True


def _announce(changes):
	rows = "".join(
		"<tr><td>{0}</td><td>{1}</td><td>{2} → {3}</td><td>{4}</td></tr>".format(
			change["idx"], frappe.bold(change["item_code"]), flt(change["from_qty"]), flt(change["qty"]), flt(change["los_qty"])
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
```

In `klik_pos/hooks.py`, make the Sales Invoice entry read:

```python
	"Sales Invoice": {
		"before_validate": "klik_pos.overrides.loss_of_sale.before_validate",
		"before_submit": "klik_pos.overrides.sales_invoice.validate_sales_person_on_submit",
```

(keep the commented `before_save` lines below as they are).

The doc_event is read from hooks at runtime. The test runner loads hooks from the installed app path, which is the main checkout. If `test_desk_submit_sells_what_is_in_stock` still fails with ERPNext's error after Step 3, the hook isn't registered in this process. In that case, add this to the runner before `unittest...run`:

```python
frappe.get_hooks("doc_events")["Sales Invoice"].setdefault("before_validate", []).append("klik_pos.overrides.loss_of_sale.before_validate")
```

Mark that line in the runner as test-only. Production reads the worktree's `hooks.py` once it is merged.

- [ ] **Step 4: Run, expect pass.** `RUN test_loss_of_sale test_loss_of_sale_split`. Expected: OK.

- [ ] **Step 5: Commit.**

```bash
git add klik_pos/overrides/loss_of_sale.py klik_pos/hooks.py klik_pos/tests/test_loss_of_sale.py
git commit -m "feat(los): an unpaid invoice submits what is in stock and records the rest

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 4: The till's checkout, sale and hold carry Loss of Sale

**Files:**
- Modify: `klik_pos/api/sales_invoice.py`:
  - `parse_invoice_data`: per-row `items.append({...})`
  - `_prepare_item_data`
  - `validate_checkout_invoice`
  - `_queue_sales_invoice`
  - module imports
- Modify: `klik_pos/api/sales_order.py`: `create_held_order`, right after the `parse_invoice_data(data)` unpacking
- Test: `klik_pos/tests/test_loss_of_sale.py` (add the Task 4 tests)

**Interfaces:**
- Consumes: `split_cart_items`, `fold_los_into_quantity` (Task 2); `before_validate` sets `allow_zero_qty` (Task 3).
- Produces: `validate_checkout_invoice` responses gain `"los_adjustments": [{index, item_code, quantity, los_qty}]`. `index` is the line's position in the request's `items`. Task 6's SPA relies on this exact shape.

- [ ] **Step 1: Write the failing tests.** Append to `TestLossOfSale`:

```python
	# Task 4 - these sell through the till, so they need an open shift.

	def _require_shift(self):
		from klik_pos.api.sales_invoice import get_current_pos_opening_entry

		if not get_current_pos_opening_entry():
			self.skipTest("no open POS Opening Entry on this site")

	def _sell(self, items, enabled=1):
		from klik_pos.api.sales_invoice import CHECKOUT_REQUEST_DOCTYPE, queue_sales_invoice
		from klik_pos.tests.pos_fixtures import payable_total, pick_payment_mode

		mode = pick_payment_mode(self.profile.name)
		total = payable_total(self.customer, items, mode)
		request_id = frappe.generate_hash(length=24)
		self.addCleanup(
			lambda: frappe.db.exists(CHECKOUT_REQUEST_DOCTYPE, request_id)
			and frappe.delete_doc(CHECKOUT_REQUEST_DOCTYPE, request_id, force=True, ignore_permissions=True)
		)
		payload = {
			"checkout_request_id": request_id,
			"customer": {"id": self.customer},
			"items": items,
			"amountPaid": total,
			"paymentMethods": [{"method": mode, "amount": total}],
			"businessType": "B2C",
		}
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=enabled):
			response = queue_sales_invoice(payload)
		if response.get("invoice_name"):
			self.addCleanup(self._drop_invoice, response["invoice_name"])
			frappe.db.commit()
		return response

	def test_the_checkout_preview_returns_the_split(self):
		self._require_shift()
		from klik_pos.api.sales_invoice import validate_checkout_invoice

		payload = {
			"customer": {"id": self.customer},
			"items": [{"id": STOCKED, "quantity": 16, "price": 100, "uom": "Nos"}],
			"businessType": "B2C",
		}
		with pos_profile_settings(self.profile.name, custom_enable_loss_of_sale=1):
			response = validate_checkout_invoice(payload)
		self.assertTrue(response["success"], response.get("message"))
		self.assertEqual(
			response["los_adjustments"], [{"index": 0, "item_code": STOCKED, "quantity": 10, "los_qty": 6}]
		)
		self.assertEqual(response["tax_preview"]["items"][0]["qty"], 10)

	def test_a_paid_sale_records_the_loss_on_its_line(self):
		self._require_shift()
		response = self._sell(
			[
				{"id": STOCKED, "quantity": 4, "los_qty": 0, "price": 100, "uom": "Nos"},
				{"id": EMPTY, "quantity": 0, "los_qty": 6, "price": 100, "uom": "Nos"},
			]
		)
		self.assertTrue(response["success"], response.get("message"))
		rows = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": response["invoice_name"]},
			fields=["item_code", "qty", "custom_los_qty"],
			order_by="idx",
		)
		self.assertEqual([(r.item_code, r.qty, r.custom_los_qty) for r in rows], [(STOCKED, 4, 0), (EMPTY, 0, 6)])
		self.assertFalse(
			frappe.db.exists("Stock Ledger Entry", {"voucher_no": response["invoice_name"], "item_code": EMPTY})
		)

	def test_a_paid_oversell_is_still_refused(self):
		self._require_shift()
		response = self._sell([{"id": STOCKED, "quantity": 16, "los_qty": 0, "price": 100, "uom": "Nos"}])
		self.assertFalse(response["success"])
		self.assertIn("Insufficient stock", response["message"])
```

- [ ] **Step 2: Run, expect failure.** `RUN test_loss_of_sale`. Expected: the preview test fails on `KeyError: 'los_adjustments'` and the paid-sale test stores no `custom_los_qty`. All three skip if no shift is open on the site. If they skip, open one in the till as Administrator before trusting the run.

- [ ] **Step 3: Carry `los_qty` through parsing and the invoice line.** In `parse_invoice_data`'s `items.append({...})`, add this after `"description": ...`:

```python
			# Asked for but not in stock: Loss of Sale, recorded on the invoice line.
			"los_qty": max(flt(item.get("los_qty") or 0), 0),
```

In `_prepare_item_data`, after the `if item.get("description"):` block:

```python
	if flt(item.get("los_qty")) > 0:
		item_data["custom_los_qty"] = flt(item.get("los_qty"))
```

- [ ] **Step 4: Split at the preview and on an unpaid sale.** At the module imports of `klik_pos/api/sales_invoice.py`, after `from klik_pos.klik_pos.utils import get_current_pos_profile`, add:

```python
from klik_pos.overrides.loss_of_sale import split_cart_items
```

In `validate_checkout_invoice`, directly after the `) = parse_invoice_data(data)` unpacking:

```python
		# Before payment: shorten lines to the stock there is and tell the till what changed.
		los_adjustments = split_cart_items(items, _get_active_pos_profile())
```

In the same function's `result = {...}`, after `"message": "Checkout validation passed",`, add `"los_adjustments": los_adjustments,`.

In `_queue_sales_invoice`, after the `if not items or len(items) == 0:` check and before `doc = build_sales_invoice_doc(`:

```python
		if not flt(amount_paid) and not loyalty_redemption and not data.get("customerCredit"):
			# Nothing taken yet (a credit sale), so it may still be shortened to the stock there
			# is. A paid sale never is: the preview split it before the money was taken.
			split_cart_items(items, _get_active_pos_profile())
```

- [ ] **Step 5: Fold on hold.** In `klik_pos/api/sales_order.py` `create_held_order`, directly after the `) = parse_invoice_data(data)` unpacking (4-space indent):

```python
        # A held order is a Sales Order, which refuses qty-0 lines: hold what was asked for.
        fold_los_into_quantity(items)
```

Add `from klik_pos.overrides.loss_of_sale import fold_los_into_quantity` to that module's imports.

- [ ] **Step 6: Run, expect pass.** `RUN test_loss_of_sale test_loss_of_sale_split test_checkout_stock_validation test_checkout_payment_scenarios test_stock_reservation`. Expected: all OK, with no new skips beyond the shift-dependent ones.

- [ ] **Step 7: Commit.**

```bash
git add klik_pos/api/sales_invoice.py klik_pos/api/sales_order.py klik_pos/tests/test_loss_of_sale.py
git commit -m "feat(los): the till's checkout splits before payment and records LoS on the line

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 5: The SPA's split rule

**Files:**
- Create: `klik_spa/src/utils/lossOfSale.ts`
- Test: `klik_spa/src/utils/lossOfSale.test.ts`

**Interfaces:**
- Produces:
  - `splitForLoS(requested, availableLeft): LineSplit`
  - `planLineQty(input: PlanInput): LineSplit | null`. It returns null when the till must refuse.
  - `applyLosAdjustments<T>(items: T[], adjustments: LosAdjustment[]): T[]`
  - `losToast(name, uom, split): string`
  - Types: `LineSplit = { quantity: number; los_qty: number }` and `LosAdjustment = { index; item_code; quantity; los_qty }`, matching Task 4's response.

- [ ] **Step 1: Write the failing test.** Create `klik_spa/src/utils/lossOfSale.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { applyLosAdjustments, losToast, planLineQty, splitForLoS } from "./lossOfSale";

const plan = (over: Partial<Parameters<typeof planLineQty>[0]> = {}) =>
  planLineQty({ limited: true, available: 10, requested: 16, otherLinesQty: 0, losEnabled: true, ...over });

describe("splitForLoS", () => {
  it("sells what is left and records the rest", () => {
    expect(splitForLoS(16, 10)).toEqual({ quantity: 10, los_qty: 6 });
  });
  it("keeps a zero line when nothing is left", () => {
    expect(splitForLoS(6, 0)).toEqual({ quantity: 0, los_qty: 6 });
  });
});

describe("planLineQty", () => {
  it("splits when LoS is on", () => {
    expect(plan()).toEqual({ quantity: 10, los_qty: 6 });
  });
  it("refuses when LoS is off", () => {
    expect(plan({ losEnabled: false })).toBeNull();
  });
  it("counts what the cart's other lines already take", () => {
    expect(plan({ otherLinesQty: 7, requested: 5 })).toEqual({ quantity: 3, los_qty: 2 });
  });
  it("leaves unlimited stock alone", () => {
    expect(plan({ limited: false, losEnabled: false })).toEqual({ quantity: 16, los_qty: 0 });
  });
  it("treats a stepper minus as a smaller request", () => {
    // "10 + LoS 6", minus one: 15 requested
    expect(plan({ requested: 15 })).toEqual({ quantity: 10, los_qty: 5 });
  });
});

describe("applyLosAdjustments", () => {
  const cart = [
    { id: "A", item_code: "A", quantity: 16, los_qty: 0 },
    { id: "B", item_code: "B", quantity: 2, los_qty: 0 },
  ];
  it("applies corrections by position", () => {
    expect(applyLosAdjustments(cart, [{ index: 0, item_code: "A", quantity: 10, los_qty: 6 }])[0]).toMatchObject({
      quantity: 10,
      los_qty: 6,
    });
  });
  it("ignores a correction whose line has moved", () => {
    expect(applyLosAdjustments(cart, [{ index: 1, item_code: "A", quantity: 10, los_qty: 6 }])).toEqual(cart);
  });
});

it("losToast names the split", () => {
  expect(losToast("Tonic", "Nos", { quantity: 10, los_qty: 6 })).toBe(
    "Only 10 Nos of Tonic in stock: 6 recorded as Loss of Sale",
  );
});
```

- [ ] **Step 2: Run, expect failure.** `cd /home/kushal/frappe-bench/apps/klik_pos-wt-los/klik_spa && npx vitest run src/utils/lossOfSale.test.ts`. Expected: it cannot resolve `./lossOfSale`.

- [ ] **Step 3: Implement.** Create `klik_spa/src/utils/lossOfSale.ts`:

```ts
/** Loss of Sale: a line asks for more than is in stock; the till sells what there is and
 * records the rest on the line. Mirrors klik_pos/overrides/loss_of_sale.py - the server's
 * checkout preview is the authority and sends corrections back (LosAdjustment). */

export interface LineSplit {
  quantity: number;
  los_qty: number;
}

export interface PlanInput {
  /** A stock item that may not go negative, with a known balance. */
  limited: boolean;
  available: number;
  requested: number;
  /** What the cart's other lines of this item already take. */
  otherLinesQty: number;
  losEnabled: boolean;
}

export interface LosAdjustment {
  index: number;
  item_code: string;
  quantity: number;
  los_qty: number;
}

const roundQty = (value: number) => Math.round(value * 1e6) / 1e6;

export function splitForLoS(requested: number, availableLeft: number): LineSplit {
  const quantity = Math.max(0, Math.min(requested, availableLeft));
  return { quantity, los_qty: roundQty(requested - quantity) };
}

/** The line's quantity and LoS for a requested amount, or null when the till must refuse it. */
export function planLineQty({ limited, available, requested, otherLinesQty, losEnabled }: PlanInput): LineSplit | null {
  if (!limited) return { quantity: requested, los_qty: 0 };
  const left = Math.max(0, available - otherLinesQty);
  if (requested <= left) return { quantity: requested, los_qty: 0 };
  return losEnabled ? splitForLoS(requested, left) : null;
}

/** The checkout preview's corrections, by position in the request - skipped for a line that is
 * no longer the item the server saw there. */
export function applyLosAdjustments<T extends { id: string; item_code?: string; quantity: number; los_qty?: number }>(
  items: T[],
  adjustments: LosAdjustment[],
): T[] {
  const byIndex = new Map(adjustments.map((adjustment) => [adjustment.index, adjustment]));
  return items.map((item, index) => {
    const adjustment = byIndex.get(index);
    if (!adjustment || (item.item_code || item.id) !== adjustment.item_code) return item;
    return { ...item, quantity: adjustment.quantity, los_qty: adjustment.los_qty };
  });
}

export const losToast = (name: string, uom: string | undefined, split: LineSplit) =>
  `Only ${split.quantity} ${uom || "units"} of ${name} in stock: ${split.los_qty} recorded as Loss of Sale`;
```

- [ ] **Step 4: Run, expect pass.** Same vitest command. Expected: all tests pass.

- [ ] **Step 5: Commit.**

```bash
cd /home/kushal/frappe-bench/apps/klik_pos-wt-los
git add klik_spa/src/utils/lossOfSale.ts klik_spa/src/utils/lossOfSale.test.ts
git commit -m "feat(spa): Loss of Sale split rule

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 6: The cart splits instead of refusing, and shows it

**Files:**
- Modify: `klik_spa/types/index.ts`: add `los_qty` to `CartItem`
- Modify: `klik_spa/src/stores/posProfileStore.ts`: add `custom_enable_loss_of_sale` to the profile type, next to `custom_use_item_code_as_display_name`
- Modify: `klik_spa/src/stores/cartStore.ts`: `addToCart`, `addToCartWithQuantity`, `updateQuantity`, `adjustQuantity`, and a new `applyCheckoutLosAdjustments`
- Modify: `klik_spa/src/components/order/CartItemRow.tsx`: qty clamp, badge, highlight
- Modify: `klik_spa/src/components/order/OrderSummary.tsx`: `startCheckoutFlow`
- Modify: `klik_spa/src/components/dialog/PaymentDialog.tsx`: tax-preview response handling

**Interfaces:**
- Consumes: `planLineQty`, `applyLosAdjustments`, `losToast` and `LosAdjustment` (Task 5); `los_adjustments` in the preview response (Task 4).
- Produces: `CartItem.los_qty?: number`. It reaches the server through PaymentDialog's existing `...item` spread and through OrderSummary's payload (Step 5).

- [ ] **Step 1: Types.** In `klik_spa/types/index.ts`, inside `CartItem` after `weight_uom?: string`:

```ts
  /** Asked for but not in stock: recorded on the invoice line as Loss of Sale. */
  los_qty?: number
```

In `klik_spa/src/stores/posProfileStore.ts`, after `custom_use_item_code_as_display_name?: boolean | number;`:

```ts
  custom_enable_loss_of_sale?: boolean | number;
```

- [ ] **Step 2: Store helpers.** In `cartStore.ts`, add this import: `import { applyLosAdjustments, losToast, planLineQty, type LosAdjustment } from '../utils/lossOfSale'`. Below `hasFiniteAvailableStock`, add:

```ts
const losEnabledFor = (item: { has_serial_no?: boolean; is_product_bundle?: boolean }) =>
  !!usePOSProfileStore.getState().posDetails?.custom_enable_loss_of_sale &&
  !item.has_serial_no &&
  !item.is_product_bundle;

const sameItemQty = (items: CartItem[], code: string, exceptId?: string) =>
  items
    .filter((cartItem) => cartItem.id !== exceptId && (cartItem.item_code || cartItem.id) === code)
    .reduce((sum, cartItem) => sum + cartItem.quantity, 0);
```

In `interface CartState`, after `adjustQuantity: ...`:

```ts
  applyCheckoutLosAdjustments: (adjustments: LosAdjustment[]) => Promise<void>
```

- [ ] **Step 3: Rewrite the four refusal points.**

**`addToCart`:** replace the `if (hasFiniteAvailableStock(item) && item.available <= 0) {...}` block and the whole `if (existingItem) {...} else {...}` body up to (not including) `await get().refreshCartPricing();` with:

```ts
        const limited = hasFiniteAvailableStock(item);
        const losEnabled = losEnabledFor(item);
        if (limited && item.available <= 0 && !losEnabled) {
          toast.error(`${item.name} is out of stock`);
          return;
        }

        if (existingItem) {
          const plan = planLineQty({
            limited,
            available: item.available ?? 0,
            requested: existingItem.quantity + (existingItem.los_qty ?? 0) + 1,
            otherLinesQty: totalMatchingQty - existingItem.quantity,
            losEnabled,
          });
          if (!plan) {
            toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
            return;
          }
          if (plan.los_qty > (existingItem.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

          const targetId = existingItem.id;
          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            plan.quantity || 1,
            existingItem.uom || item.uom,
          );

          set((state) => {
            const updated = state.cartItems.map((cartItem) =>
              cartItem.id === targetId
                ? {
                    ...cartItem,
                    quantity: plan.quantity,
                    los_qty: plan.los_qty,
                    item_tax_template: taxDetails.item_tax_template,
                    item_tax_rate: taxDetails.item_tax_rate,
                    tax_templates: taxDetails.tax_templates,
                    total_tax_rate: taxDetails.total_tax_rate,
                  }
                : cartItem
            );
            return {
              cartItems: reorderToInsertionPosition(updated, targetId),
              highlightItemId: targetId,
              highlightNonce: state.highlightNonce + 1,
            };
          });
        } else {
          const plan = planLineQty({
            limited,
            available: item.available ?? 0,
            requested: 1,
            otherLinesQty: totalMatchingQty,
            losEnabled,
          });
          if (!plan) return;
          if (plan.los_qty > 0) toast.warning(losToast(item.name, item.uom, plan));

          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            1,
            item.uom,
          );

          const newItem = {
            ...item,
            quantity: plan.quantity,
            los_qty: plan.los_qty,
            bundle_entries: [],
            item_tax_template: taxDetails.item_tax_template,
            item_tax_rate: taxDetails.item_tax_rate,
            tax_templates: taxDetails.tax_templates,
            total_tax_rate: taxDetails.total_tax_rate,
          };
          const newCartItems = shouldInsertNewItemsAtTop()
            ? [newItem, ...state.cartItems]
            : [...state.cartItems, newItem];
          set((s) => ({
            cartItems: newCartItems,
            highlightItemId: newItem.id,
            highlightNonce: s.highlightNonce + 1,
          }));
        }
```

**`addToCartWithQuantity`:** replace both refusal blocks (`if (hasFiniteAvailableStock(item) && item.available < quantity) {...}` and, inside `if (existingItem)`, the `(totalMatchingQty + quantity) > item.available` block). Put this before `let lineId: string;`:

```ts
        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested: existingItem ? existingItem.quantity + (existingItem.los_qty ?? 0) + quantity : quantity,
          otherLinesQty: totalMatchingQty - (existingItem?.quantity ?? 0),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
          return null;
        }
        if (plan.los_qty > (existingItem?.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));
```

Then, in the existing-line branch, make these changes:
- `const updatedQty = existingItem.quantity + quantity;` becomes `const updatedQty = plan.quantity;`
- `fetchItemTaxDetails(..., updatedQty, ...)` becomes `fetchItemTaxDetails(..., updatedQty || 1, ...)`
- The mapped object gains `los_qty: plan.los_qty,` after `quantity: updatedQty,`

In the new-line branch:
- `fetchItemTaxDetails(incomingCode, customerId, quantity, item.uom)` becomes `fetchItemTaxDetails(incomingCode, customerId, plan.quantity || 1, item.uom)`
- `newItem`'s `quantity,` becomes `quantity: plan.quantity, los_qty: plan.los_qty,`

**`updateQuantity`:** replace from `const item = state.cartItems.find(...)` to the end of the `set({...})` call with:

```ts
        const item = state.cartItems.find((cartItem) => cartItem.id === id);
        if (!item) return;
        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested: quantity,
          otherLinesQty: sameItemQty(state.cartItems, item.item_code || item.id, id),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
          return;
        }
        if (plan.los_qty > (item.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

        set({
          cartItems: state.cartItems.map((cartItem) =>
            cartItem.id === id ? { ...cartItem, quantity: plan.quantity, los_qty: plan.los_qty } : cartItem
          )
        });
```

**`adjustQuantity`:** replace from `const newQuantity = item.quantity + delta;` to the end of its `set((s) => ({...}));` with:

```ts
        const requested = item.quantity + (item.los_qty ?? 0) + delta;

        if (requested <= 0) {
          get().removeItem(id);
          return;
        }

        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested,
          otherLinesQty: sameItemQty(state.cartItems, item.item_code || item.id, id),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.warning(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available.`);
          return;
        }
        if (plan.los_qty > (item.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

        set((s) => ({
          cartItems: s.cartItems.map((cartItem) =>
            cartItem.id === id ? { ...cartItem, quantity: plan.quantity, los_qty: plan.los_qty } : cartItem
          ),
          highlightItemId: id,
          highlightNonce: s.highlightNonce + 1,
        }));
```

**New action**, after `adjustQuantity`:

```ts
      applyCheckoutLosAdjustments: async (adjustments) => {
        if (!adjustments?.length) return;
        set((s) => ({ cartItems: applyLosAdjustments(s.cartItems, adjustments) }));
        toast.warning(
          adjustments.length === 1
            ? `Stock changed: 1 line shortened, the rest recorded as Loss of Sale`
            : `Stock changed: ${adjustments.length} lines shortened, the rest recorded as Loss of Sale`,
        );
        await get().refreshCartPricing();
      },
```

- [ ] **Step 4: Cart row.** In `CartItemRow.tsx`:
  - The `useEffect` that syncs `localQty` gets `item.los_qty` as a dependency: `}, [item.quantity, item.los_qty]);`
  - In the qty input's `onBlur`, the clamp condition gains `!posDetails?.custom_enable_loss_of_sale &&` at the front. The `else` branch becomes `{ onUpdateQuantity(item.id, localQty); setLocalQty(item.quantity); }`. With LoS on, the store splits the request, and `item.quantity` plus the effect show the result.
  - The outer row `div` (`data-cart-item-id={itemId}` with `transition-colors hover:...`) gets `${(item.los_qty ?? 0) > 0 ? "bg-amber-50/70 dark:bg-amber-900/10" : ""}` added to its className template.
  - Under the item-code line, inside `<div className="min-w-0 flex-1">` after the `custom_show_item_code_in_product_list` block:

```tsx
              {(item.los_qty ?? 0) > 0 && (
                <span
                  className="mt-0.5 inline-block rounded bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                  title="Asked for but not in stock: recorded as Loss of Sale"
                >
                  LoS {item.los_qty}
                </span>
              )}
```

- [ ] **Step 5: Preview corrections.** In `OrderSummary.tsx` `startCheckoutFlow`:
  - The payload's item map gains `los_qty: item.los_qty ?? 0,` after `quantity: item.quantity,`.
  - Replace `await validateCheckoutInvoice(payload);` with:

```ts
      const result = await validateCheckoutInvoice(payload);
      await useCartStore.getState().applyCheckoutLosAdjustments(result?.los_adjustments ?? []);
```

In `PaymentDialog.tsx`, in the tax-preview handler, directly after `const response = await pending;`:

```ts
        if (response?.los_adjustments?.length) {
          void useCartStore.getState().applyCheckoutLosAdjustments(response.los_adjustments);
        }
```

Import `useCartStore` there if the file does not already.

- [ ] **Step 6: Verify the build.** From `klik_spa/`, run each of these:
  - `npx tsc --noEmit -p tsconfig.app.json`: no new errors versus the same command on `develop`.
  - `npx eslint src/stores/cartStore.ts src/components/order/CartItemRow.tsx src/components/order/OrderSummary.tsx src/components/dialog/PaymentDialog.tsx src/utils/lossOfSale.ts`: no new errors relative to `develop`.
  - `npx vitest run`: all pass.

- [ ] **Step 7: Browser check.**
  1. Run `npx vite --port 8092 --strictPort` from the worktree's `klik_spa` (in the background).
  2. In the playwright MCP browser, open `http://dev.localhost:8092/klik_pos/pos`. The API is served by the main checkout, which lacks the server half until merge, so this checks the cart only.
  3. Turn `custom_enable_loss_of_sale` on for the till's POS Profile in Desk (`/app/pos-profile/<name>`) and reload the till.
  4. Pick an item with a small stock N. Type N+6 in the grid and add it. Expect: a line of N, an amber row, an "LoS 6" badge, and the toast "Only N … in stock: 6 recorded as Loss of Sale".
  5. Press − once: expect LoS 5. Press + twice: expect LoS 7.
  6. Turn the flag off again afterwards.
  7. Take a screenshot as evidence. Stop the vite server.

- [ ] **Step 8: Commit.**

```bash
cd /home/kushal/frappe-bench/apps/klik_pos-wt-los
git add klik_spa/types/index.ts klik_spa/src/stores/posProfileStore.ts klik_spa/src/stores/cartStore.ts klik_spa/src/components/order/CartItemRow.tsx klik_spa/src/components/order/OrderSummary.tsx klik_spa/src/components/dialog/PaymentDialog.tsx
git commit -m "feat(spa): the cart sells what is in stock and records the rest as Loss of Sale

Claude-Session: https://claude.ai/code/session_01Lw99uJkPYfee5gFWvEcKu7"
```

---

### Task 7: Whole-branch verification, review, landing

- [ ] **Step 1: Run every Python suite this branch touches.** Check for another session's run first.

`RUN test_loss_of_sale test_loss_of_sale_split test_checkout_stock_validation test_checkout_payment_scenarios test_stock_reservation test_stock_by_warehouse test_server_side_hiding test_held_order_tax_treatment`

Expected: OK. Any skip must be shift-related and must be stated in the summary.

- [ ] **Step 2: Run the SPA checks.** `cd klik_spa && npx tsc --noEmit -p tsconfig.app.json && npx vitest run`.

- [ ] **Step 3: Request code review.** Use superpowers:requesting-code-review on `git diff develop...feat/loss-of-sale` with the spec and this plan. Fix Blocker and Major findings and list the rest.

- [ ] **Step 4: Land.** Use superpowers:finishing-a-development-branch. Per the user's CLAUDE.md, merge into `develop` with `--no-ff` and push to `upstream/develop`, working from the worktree because the main checkout is busy. Fields appear on the next `bench migrate`, through the `after_migrate` hook.
  - Remove the worktree's `node_modules` symlinks before `git worktree remove`.
  - State what was pushed and where.
