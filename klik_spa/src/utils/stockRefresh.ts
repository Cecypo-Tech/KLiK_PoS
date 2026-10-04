import type { MenuItem } from "../../types";

/** Whether an item's `available` is a raw stock figure (not a bundle's component limit or a
template's variant count, which the listing computes and a Bin read would clobber). */
function isPlainStockItem(product: MenuItem): boolean {
  return product.is_stock_item !== false && !product.is_product_bundle && !product.is_variant_template;
}

/** The items whose stock the background refresh asks for. */
export function stockRefreshCodes(products: MenuItem[]): string[] {
  return products.filter(isPlainStockItem).map((product) => product.id);
}

/** Split codes into requests of at most `size` (keeps each request body small). */
export function chunkCodes(codes: string[], size: number): string[][] {
  const chunks: string[][] = [];
  for (let start = 0; start < codes.length; start += size) {
    chunks.push(codes.slice(start, start + size));
  }
  return chunks;
}

/**
 * Merge fresh stock figures without touching items that did not change, and return the
 * very same list when nothing did - the grid's memoized cards then redraw nothing.
 * The server reports stock-UOM quantities; the listing shows `balance // conversion_factor`
 * for items sold in another UOM, so the same floor is applied here.
 */
export function applyStockUpdates(products: MenuItem[], updates: Record<string, number>): MenuItem[] {
  let changed = false;
  const next = products.map((product) => {
    if (!(product.id in updates) || !isPlainStockItem(product)) return product;
    const raw = Number(updates[product.id]);
    if (!Number.isFinite(raw)) return product;
    const value = Math.floor(raw / (product.conversion_factor || 1));
    if (value === product.available) return product;
    changed = true;
    return { ...product, available: value };
  });
  return changed ? next : products;
}
