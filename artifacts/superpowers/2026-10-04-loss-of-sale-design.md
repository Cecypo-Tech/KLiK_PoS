# Loss of Sale (LoS) — design

Date: 2026-10-04 · Status: design approved, spec under review

## Context
A customer asks for 16, the warehouse has 10. Today the till refuses with "Only 10 … available", and Desk refuses at submit with ERPNext's "6 units of Item X needed in Warehouse Y". The sale either fails or the cashier retypes it, and the unmet demand is never recorded. The old system recorded it as **Loss of Sale**. Goal: sell what's in stock, and record the shortfall per line so requested vs supplied can be reported.

Decisions made with the user:
- **Record:** a read-only field on Sales Invoice Item, not an SO→SI flow. Requested = Qty + LoS Qty.
- **Zero stock:** keep the line with Qty 0 and LoS = requested. ERPNext allows this through `flags.allow_zero_qty`, and `selling_controller.update_stock_ledger` already skips rows with qty 0.
- **Scope:** till only. LoS applies to invoices whose POS Profile has it switched on. Desk invoices carrying such a profile get it too; other Desk invoices are unchanged.
- **Reporting:** the column only (Report View on Sales Invoice Item covers ad-hoc queries).

## Fields
- **POS Profile** `custom_enable_loss_of_sale` (Check). Add it to `POS_PROFILE_FEATURE_FIELDS` in `klik_pos/setup/pos_profile_fields.py`, after `allow_warehouse_change`. The SPA reads it from `get_pos_details`, which returns `as_dict()`.
- **Sales Invoice Item** `custom_los_qty` (Float). Properties: read_only, in_list_view (visible in the items grid), no_copy (returns and copies don't carry it), print_hide. Insert after `qty`. Created by a new `ensure_*` function called from `ensure_pos_profile_feature_fields`. This is the first klik field on that child table.

## The split rule (one rule, server and SPA)
For each eligible line, requested = qty + los_qty. Available stock is shared across all lines of the same item and warehouse, and lines are filled in row order: line qty = min(requested, what's left), and los_qty = requested − qty. Quantities are converted through `conversion_factor`, and floored when the UOM must be a whole number. Re-running the split gives the same result, so the rule can run more than once safely.

**Eligible line:** a stock item, without `allow_negative_stock`, not serial-numbered, not a product bundle, without a serial/batch bundle already attached, on an invoice that has `update_stock=1` and is not a return. Ineligible lines keep today's behaviour.

**Available stock** = Bin actual minus reservations. The availability calculation will be pulled out of `_validate_reserved_stock_for_items` (`klik_pos/api/sales_invoice.py`) into a shared helper, so the split and the existing refusal can never disagree.

If no line has qty > 0 after the split, the sale is refused with "Nothing on this sale is in stock": a zero-value invoice is not created. *(Open: see the end.)*

## Server
New module `klik_pos/overrides/loss_of_sale.py`. `apply_loss_of_sale(doc)` returns the list of changes `[{idx, item_code, from_qty, qty, los_qty}]`. It sets `doc.flags.allow_zero_qty` only when it created qty-0 rows, and throws for any other qty-0 row.

It is called from three places:
1. **`validate_checkout_invoice`** (the pre-payment preview when Checkout is pressed), before `_validate_reserved_stock_for_items`. The response gains `los_adjustments`, so the cart is corrected **before any money is taken**.
2. **`_queue_sales_invoice`, only when nothing is paid** (credit sale), before the stock validation.
3. **`CustomSalesInvoice.before_validate`, when `_action == "submit"` and `paid_amount == 0`.** This covers Desk invoices. It replaces ERPNext's "units needed" dialog with an orange `msgprint` table: "Row 3: H035 89 → 40, 49 recorded as Loss of Sale".

**Paid invoices are never shrunk after payment.** If stock drops between the preview and submit, today's refusal stands, so payments are never left unbalanced.

- **Payload:** add `los_qty` to the per-row whitelist in `parse_invoice_data` (`sales_invoice.py`) and write it as `custom_los_qty` in `_prepare_item_data`.
- **Held orders:** carry `los_qty` in `custom_klik_cart_meta` (`sales_order.py` `_build_cart_meta` and `get_held_order_details`). No Sales Order field is needed.

## SPA
- **`klik_spa/src/utils/lossOfSale.ts`** (new): a pure function `splitForLoS(requested, availableLeft)` returning `{qty, los_qty}`, with vitest coverage.
- **`cartStore.ts`:** when `posDetails.custom_enable_loss_of_sale` is on, the stock refusals in `addToCart`, `addToCartWithQuantity`, `updateQuantity` and `adjustQuantity` (six branches across the four) split instead of refusing. Any qty change (typed, stepper, add) sets a new *requested* and re-splits: a − on "10 + LoS 6" gives "10 + LoS 5". The toast reads "Only 10 in stock: 6 recorded as Loss of Sale". The cart-row clamp at `CartItemRow.tsx` is dropped in favour of the store's split.
- **`CartItemRow.tsx`:** rows with LoS get an amber highlight and an "LoS 6" badge.
- **`OrderSummary.tsx`:** applies `los_adjustments` from the checkout preview to the cart, with a toast, before payment opens.
- **Types and resume:** `los_qty?: number` on `CartItem` (`klik_spa/types/index.ts`), the flag on `POSDetails`, and `heldOrderToCart.ts` restoring `los_qty`. Resumed held lines carry no `available`, so the server preview re-splits them.
- `PaymentDialog` already spreads `...item`, so `los_qty` reaches the server without changes there.
- The cart's split is a convenience and the checkout preview is the authority. The cart's `available` is in the listing UOM, but scanned items report the stock UOM, and a UOM change in the cart doesn't rescale it. Those cases can split wrongly in the cart, and the preview corrects them before payment.

## Not in v1
- Serial-numbered items and product bundles (they keep today's refusal).
- A Desk-wide switch for invoices without a profile.
- An LoS report.
- Amending a cancelled invoice loses the LoS split, because of no_copy.

## Verification
- **Python unit tests** (new `klik_pos/tests/test_loss_of_sale.py`):
  - partial shortage (16 asked, 10 in stock → 10 + 6)
  - zero stock (qty 0, LoS 6, invoice submits, no ledger row)
  - two rows of the same item sharing stock
  - UOM conversion and the whole-number floor
  - profile switched off: no change
  - paid invoice at submit: refused as today
  - idempotent re-run
  - stock reservations respected
  - all-zero sale refused
- **Integration:** submit a credit Sales Invoice with an LoS profile, check the stored qty / `custom_los_qty` and the stock ledger. Existing suites stay green: `test_checkout_stock_validation`, `test_stock_reservation`, `test_checkout_payment_scenarios`.
- **vitest** for `splitForLoS` and the cartStore actions.
- **Browser check on dev.localhost:** type 16 against stock 10 and see the row become 10 with an amber LoS 6 badge and a toast; checkout; then in Desk the invoice shows the LoS Qty column. Desk: a draft with 89 against 40 submits with the msgprint instead of ERPNext's error.

## Open question for spec review
When nothing on the sale is in stock, v1 refuses, so a customer who leaves with nothing records no LoS. Recording that case needs either a zero-value invoice or a separate LoS log. It is deferred unless you want it now.
