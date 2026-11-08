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
  // A custom rate is restored by the caller regardless; the discount beside it follows the
  // same rule as any line's, since it now comes off the custom rate too.
  const price = Number(item.price || 0);
  const original = Number(item.original_price || 0);

  return !(original > price);
}
