/** Cart state that lives only while the page is open: never saved, so a reload neither
 * reopens a panel nor replays a request. */
const TRANSIENT = ["expandedCartItemId", "pendingRateOverrides", "rateOverrideNonce", "additionalInfoOpen"] as const;

export function persistedCartState<T extends object>(state: T): Omit<T, (typeof TRANSIENT)[number]> {
  const saved = { ...state } as Record<string, unknown>;
  for (const key of TRANSIENT) delete saved[key];
  return saved as Omit<T, (typeof TRANSIENT)[number]>;
}
