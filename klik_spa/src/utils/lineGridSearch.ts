import { toast } from "react-toastify";
import { useCartStore } from "../stores/cartStore";
import { useProductStore } from "../stores/productStore";
import type { MenuItem } from "../../types";

export const STALE: unique symbol = Symbol("stale");

/** Only the most recently wrapped promise resolves to its value; earlier ones resolve to STALE. Does not swallow rejections. */
export function latestOnly<T>() {
  let latest = 0;
  return async (p: Promise<T>): Promise<T | typeof STALE> => {
    const mine = ++latest;
    const v = await p;
    return mine === latest ? v : STALE;
  };
}

/** Item dropdown search for the grid. Calls the API directly so productStore state is never touched. */
export async function searchGridItems(query: string): Promise<MenuItem[]> {
  const ps = useProductStore.getState();
  const { items } = await ps.fetchProductsFromAPI(8, 0, query, "all", ps.getEffectiveCustomer()?.id || "", ps.getEffectivePriceList());
  return items;
}

export type ScanResult = { lineId: string } | { notFound: true } | { refused: true };

let scanTail: Promise<unknown> = Promise.resolve();

async function run(code: string): Promise<ScanResult> {
  const item = await useProductStore.getState().fetchItemByIdentifier(code);
  if (!item) {
    toast.error(`No item found for ${code}`);
    return { notFound: true };
  }
  const lineId = await useCartStore.getState().addToCartQueued({ ...item, item_code: item.id } as never);
  return lineId ? { lineId } : { refused: true };
}

/** Resolve a scanned code and add it. Scans are serialised (lookup included) so lines land in scan order.
 * Ignores auto_add_item_to_cart and custom_use_scanner_fully. */
export function scanAdd(code: string): Promise<ScanResult> {
  const result = scanTail.then(() => run(code));
  scanTail = result.catch(() => undefined); // a failed scan must not break the chain
  return result;
}
