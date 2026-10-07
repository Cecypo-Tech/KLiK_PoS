/** Rate-override requests from outside the cart UI (the item list's '*' shortcut, quick
 * entry), queued for OrderSummary to apply. See cartStore.pendingRateOverrides. */
export interface RateOverride {
  itemId: string;
  rate: number;
  includesTax: boolean;
  /** The price list the rate was picked from; absent for a typed price. */
  priceList?: string;
  nonce: number;
}

export function enqueueRateOverride(
  queue: RateOverride[],
  lastNonce: number,
  request: Omit<RateOverride, "nonce">
): { queue: RateOverride[]; nonce: number } {
  const nonce = lastNonce + 1;
  return { queue: [...queue, { ...request, nonce }], nonce };
}

/** The queue without the requests up to and including `nonce`, once applied. */
export function consumeRateOverrides(queue: RateOverride[], nonce: number): RateOverride[] {
  return queue.filter((o) => o.nonce > nonce);
}

/** The cart line's discount entry once the override is applied, as the cart's own Rate field
 * and price-list switch would leave it: the line shows the price list the rate came from, or
 * none for a typed price - not the cart's default list beside a different rate. */
export function discountForOverride<T extends object>(prev: T | undefined, override: RateOverride) {
  return {
    ...(prev ?? {}),
    customRate: override.rate,
    customRateIncludesTax: override.includesTax,
    discountPercentage: 0,
    discountAmount: 0,
    selectedPriceList: override.priceList ?? "",
  };
}
