import { roundCurrency } from "./currencyMath";

/**
 * Amounts after ticking `methodId` on in the payment methods list.
 *
 * Ticking a row fills what the sale still owes. When nothing is owed because one other
 * row already holds exactly the whole sale - the default Cash row is pre-filled with the
 * total - ticking means "pay this way instead", so that amount moves to the ticked row.
 * A split across several rows, a row holding more than the sale (cash tendered with
 * change), or a row money already arrived for (picked receipts, a completed STK push) is
 * left as it is.
 */
export function toggleOn(
  amounts: Record<string, number>,
  methodId: string,
  payable: number,
  /** Rows backed by picked receipts or a completed STK push: never emptied by a toggle. */
  lockedIds: string[] = [],
): Record<string, number> {
  const others = Object.entries(amounts).filter(([id, v]) => id !== methodId && (Number(v) || 0) > 0);
  const othersTotal = others.reduce((sum, [, v]) => sum + (Number(v) || 0), 0);
  const remaining = roundCurrency(Math.max(0, payable - othersTotal));
  if (remaining > 0 || others.length !== 1) return { ...amounts, [methodId]: remaining };

  const holder = others[0];
  if (!holder || roundCurrency(Number(holder[1])) !== roundCurrency(payable)) return { ...amounts, [methodId]: 0 };
  const [holderId] = holder;
  if (lockedIds.includes(holderId)) return { ...amounts, [methodId]: 0 };
  return { ...amounts, [holderId]: 0, [methodId]: roundCurrency(payable) };
}

/**
 * Amounts after the sale's total changed - a discount, a delivery charge, a coupon.
 *
 * The one method that paid the whole previous total pays the new total, whichever method it
 * is: M-Pesa ticked for 560 and then discounted to 4 must ask the customer for 4, not 560. A
 * split, an amount the cashier set away from the total, or `locked` (a method whose money is
 * already asked for or paid - an M-Pesa push waiting or completed) is left as it is.
 */
export function followTotal(
  prev: Record<string, number>,
  previousTotal: number,
  newTotal: number,
  locked?: string | null,
): Record<string, number> {
  const paying = Object.entries(prev).filter(([, amount]) => Number(amount) > 0);
  if (paying.length !== 1) return prev;
  const [method, amount] = paying[0] as [string, number];
  if (method === locked) return prev;
  if (Math.abs(roundCurrency(Number(amount)) - roundCurrency(previousTotal)) > 0.01) return prev;
  return { ...prev, [method]: roundCurrency(newTotal) };
}
