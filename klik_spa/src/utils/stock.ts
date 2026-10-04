import type { MenuItem } from "../../types";

/**
 * Single source of truth for the POS "out of stock" gate.
 *
 * An item is out of stock only when it is a stock item, has no available
 * quantity, and is NOT flagged to allow negative stock. Service items
 * (is_stock_item === false) and items with allow_negative_stock are always
 * sellable regardless of on-hand quantity.
 */
export const isItemOutOfStock = (
  item: Pick<MenuItem, "is_stock_item" | "available" | "allow_negative_stock" | "has_serial_no" | "is_product_bundle">,
  stockUnavailable = false,
  losEnabled = false,
): boolean => {
  // Loss of Sale: the cart sells what is there and records the shortfall (mirrors
  // losEnabledFor in cartStore), so an empty shelf does not block the add.
  if (losEnabled && !item.has_serial_no && !item.is_product_bundle) {
    return false;
  }

  // Stock could not be read (no permission on Bin), so every balance arrives as 0. Treating
  // that as "out of stock" would grey out and block the entire catalogue - worse than the
  // empty grid it replaced. Unknown is not the same as none: leave items sellable and let
  // the degradation banner explain why the figures are missing.
  if (stockUnavailable) {
    return false;
  }

  return (
    item.is_stock_item !== false &&
    (item.available ?? 0) <= 0 &&
    !item.allow_negative_stock
  );
};
