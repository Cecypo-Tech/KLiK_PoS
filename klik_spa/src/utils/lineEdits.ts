/** Rate/discount rules shared by the cart row and the line-entry grid. */

export function discountAmountFromPct(price: number, pct: number): number {
  const p = Math.min(100, Math.max(0, pct || 0));
  return parseFloat(((price * p) / 100).toFixed(2));
}

export function discountPctFromAmount(price: number, amount: number): number {
  return price > 0 ? parseFloat(((amount / price) * 100).toFixed(2)) : 0;
}

/** Lifts a rate under the till's minimum (see rateBoxMinimum) to it; null = no floor. */
export function clampRateToFloor(rate: number, minimum: number | null): number {
  return minimum !== null && rate < minimum ? minimum : rate;
}
