/** Cart state that lives only while the page is open: never saved, so a reload neither
 * reopens a panel nor replays a request. */
const TRANSIENT = ["expandedCartItemId", "pendingRateOverrides", "rateOverrideNonce", "additionalInfoOpen"] as const;

/** The order itself. Once its sale is complete none of it is saved: the Order Complete
 * screen still shows it, but a reload starts empty instead of offering the sale again. */
const ORDER = [
  "cartItems",
  "appliedCoupons",
  "selectedCustomer",
  "walkinDetails",
  "extraFields",
  "selectedPriceList",
  "shippingRule",
  "checkoutExtras",
  "saleCompleted",
  "creditSale",
] as const;

export function persistedCartState<T extends object>(state: T): Omit<T, (typeof TRANSIENT)[number]> {
  const saved = { ...state } as Record<string, unknown>;
  for (const key of TRANSIENT) delete saved[key];
  if (saved.saleCompleted) for (const key of ORDER) delete saved[key];
  return saved as Omit<T, (typeof TRANSIENT)[number]>;
}
