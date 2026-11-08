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

/** The result whose code (item_code, else id) is exactly the typed text: an item code typed and
 * Entered is a scan, though the identifier lookup only knows barcodes, batches and serials. */
export function exactCodeMatch(list: MenuItem[], q: string): MenuItem | undefined {
  const want = q.trim().toLowerCase();
  return list.find((r) => (r.item_code || r.id).toLowerCase() === want);
}

/** `pick`: a variant template, for the caller's variant picker; it is never added itself. */
export type ScanResult = { lineId: string } | { notFound: true } | { refused: true } | { pick: MenuItem };

const LOOKUP_TIMEOUT_MS = 8000;
let scanTail: Promise<unknown> = Promise.resolve();

async function run(code: string, quiet: boolean): Promise<ScanResult> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timedOut = new Promise<"timeout">((r) => (timer = setTimeout(() => r("timeout"), LOOKUP_TIMEOUT_MS)));
  // A lookup that never answers must not hold up every later scan in the chain.
  const item = await Promise.race([useProductStore.getState().fetchItemByIdentifier(code), timedOut])
    .finally(() => clearTimeout(timer));
  if (item === "timeout") {
    toast.error(`Lookup for ${code} timed out`);
    return { notFound: true };
  }
  if (!item) {
    if (!quiet) toast.error(`No item found for ${code}`);
    return { notFound: true };
  }
  if (item.has_variants || item.is_variant_template) return { pick: item };
  // A scan always merges: allow_multiple_items is for typed picks only.
  const lineId = await useCartStore.getState().addToCartQueued({ ...item, item_code: item.id } as never, { merge: true });
  return lineId ? { lineId } : { refused: true };
}

/** Resolve a scanned code and add it. Scans are serialised (lookup included) so lines land in scan order.
 * Always merges into an existing line of the item. Ignores auto_add_item_to_cart and custom_use_scanner_fully. `quiet`: no "not found" toast, for a
 * caller with a typed-search pick to fall back on. */
export function scanAdd(code: string, { quiet = false } = {}): Promise<ScanResult> {
  const result = scanTail.then(() => run(code, quiet));
  scanTail = result.catch(() => undefined); // a failed scan must not break the chain
  return result;
}
