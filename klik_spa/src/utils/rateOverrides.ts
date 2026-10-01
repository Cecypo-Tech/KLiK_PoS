/** Rate-override requests from outside the cart UI (the item list's '*' shortcut, quick
 * entry), queued for OrderSummary to apply. See cartStore.pendingRateOverrides. */
export interface RateOverride {
  itemId: string;
  rate: number;
  includesTax: boolean;
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
