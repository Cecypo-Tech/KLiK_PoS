import type { MenuItem } from "../../types";

/** The till's hide-unavailable rule: a stock item with nothing on hand is hidden unless it
may go negative. Hiding off returns the very list it was given. */
export function filterAvailableProducts(products: MenuItem[], hideUnavailable: boolean): MenuItem[] {
  if (!hideUnavailable) return products;
  return products.filter((product) => {
    const isStockItem = product.is_stock_item !== false;
    if (!isStockItem || product.allow_negative_stock) return true;
    return (product.available || 0) > 0;
  });
}
