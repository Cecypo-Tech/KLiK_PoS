import type { CartItem } from "../../types";
import { losToast, planLineQty } from "./lossOfSale";

export interface BulkEntry {
  item: Omit<CartItem, "quantity">;
  qty: number;
}

interface Helpers {
  limited: (item: Omit<CartItem, "quantity">) => boolean;
  losEnabled: (item: Omit<CartItem, "quantity">) => boolean;
  insertAtTop: boolean;
}

/** The line moved to where the till puts new lines (top or bottom). */
export function moveLine(items: CartItem[], id: string, top: boolean): CartItem[] {
  const moved = items.find((i) => i.id === id);
  if (!moved) return items;
  const rest = items.filter((i) => i !== moved);
  return top ? [moved, ...rest] : [...rest, moved];
}

/**
 * addToCartWithQuantity's merge for many entries at once: each entry reads the cart the one
 * before it left, stock and Loss of Sale planned the same way. Tax details come on the item
 * (quick entry's server attaches them), so nothing here waits on the network.
 */
export function addEntries(cartItems: CartItem[], entries: BulkEntry[], helpers: Helpers) {
  let items = [...cartItems];
  const lineIds: Array<string | null> = [];
  const warnings: string[] = [];
  const refusals: string[] = [];
  for (const { item, qty } of entries) {
    const code = item.item_code || item.id;
    const existing = items.find((c) => c.id === item.id || (c.item_code || c.id) === code);
    const sameItemQty = items.filter((c) => (c.item_code || c.id) === code).reduce((sum, c) => sum + c.quantity, 0);
    const plan = planLineQty({
      limited: helpers.limited(item),
      available: item.available ?? 0,
      requested: existing ? existing.quantity + (existing.los_qty ?? 0) + qty : qty,
      otherLinesQty: sameItemQty - (existing?.quantity ?? 0),
      losEnabled: helpers.losEnabled(item),
    });
    if (!plan) {
      refusals.push(`Only ${item.available} ${item.uom || "units"} of ${item.name} available`);
      lineIds.push(null);
      continue;
    }
    if (plan.los_qty > (existing?.los_qty ?? 0)) warnings.push(losToast(item.name, item.uom, plan));
    const tax = {
      item_tax_template: item.item_tax_template,
      item_tax_rate: item.item_tax_rate,
      tax_templates: item.tax_templates,
      total_tax_rate: item.total_tax_rate,
    };
    if (existing) {
      items = items.map((c) => (c.id === existing.id ? { ...c, ...tax, quantity: plan.quantity, los_qty: plan.los_qty } : c));
      items = moveLine(items, existing.id, helpers.insertAtTop);
      lineIds.push(existing.id);
    } else {
      const line = { ...item, quantity: plan.quantity, los_qty: plan.los_qty, bundle_entries: [] } as CartItem;
      items = helpers.insertAtTop ? [line, ...items] : [...items, line];
      lineIds.push(line.id);
    }
  }
  return { cartItems: items, lineIds, warnings, refusals };
}
