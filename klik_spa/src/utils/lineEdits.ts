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

/** A fraction typed in a unit marked Must be Whole Number (ERPNext's UOM setting), which ERPNext refuses on save. */
export function fractionInWholeUnit(qty: number, uom: string | undefined, wholeUoms: string[] | undefined): boolean {
  return Math.abs(qty - Math.round(qty)) > 1e-7 && !!uom && !!wholeUoms?.includes(uom);
}

/** The invoice discount once the subtotal moves, as ERPNext's: given in %, the % holds and the
 * amount follows; given as an amount, the amount holds and the % follows. */
export function rebaseOrderDiscount(
  d: { byPercent: boolean; percent: number; amount: number },
  subtotal: number,
): { percent: number; amount: number } {
  if (d.byPercent) return { percent: d.percent, amount: Math.round(subtotal * d.percent) / 100 };
  return { percent: subtotal > 0 ? discountPctFromAmount(subtotal, d.amount) : 0, amount: d.amount };
}
