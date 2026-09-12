/**
 * Whether a discount stored on a cart item still needs applying, or has already been
 * taken off the price.
 *
 * `item.price` means two different things depending on where the item came from, and
 * that ambiguity was double-discounting reloaded carts. `refreshCartPricing` writes the
 * rule-discounted rate into `price` and *also* leaves `discount_amount` on the item, so
 * rehydrating the cart from localStorage and seeding `itemDiscounts` from that field
 * subtracted the same discount a second time: 20 x 2,000 became 20 x 1,900 purely by
 * refreshing the page, and every refresh after that was another chance to drift.
 *
 * `original_price` is the tell. It is only ever written next to an already-discounted
 * `price`, so `original_price > price` means the discount is spent and must not be
 * restored. A held order or draft carries its discount without an `original_price`, and
 * those still restore exactly as before.
 */

export interface PersistedDiscountFields {
  price?: number;
  original_price?: number;
  discount_amount?: number;
  discount_percentage?: number;
  custom_rate?: number | null;
}

export function shouldRestorePersistedDiscount(item: PersistedDiscountFields): boolean {
  // A custom rate is the cashier's own number. Pricing never folds it into `price`, so
  // it always has to be restored, whatever a rule did alongside it.
  if (item.custom_rate !== undefined && item.custom_rate !== null) return true;

  const price = Number(item.price || 0);
  const original = Number(item.original_price || 0);

  return !(original > price);
}
