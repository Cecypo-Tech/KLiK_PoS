import { roundCurrency } from "./currencyMath";

/**
 * Amounts after ticking `methodId` on in the payment methods list.
 *
 * Ticking a row fills what the sale still owes. When nothing is owed because one other
 * row already holds exactly the whole sale - the default Cash row is pre-filled with the
 * total - ticking means "pay this way instead", so that amount moves to the ticked row.
 * A split across several rows, or a row holding more than the sale (cash tendered with
 * change), is the cashier's own arithmetic and stays as it is.
 */
export function toggleOn(amounts: Record<string, number>, methodId: string, payable: number): Record<string, number> {
  const others = Object.entries(amounts).filter(([id, v]) => id !== methodId && (Number(v) || 0) > 0);
  const othersTotal = others.reduce((sum, [, v]) => sum + (Number(v) || 0), 0);
  const remaining = roundCurrency(Math.max(0, payable - othersTotal));
  if (remaining > 0 || others.length !== 1) return { ...amounts, [methodId]: remaining };

  const holder = others[0];
  if (!holder || roundCurrency(Number(holder[1])) !== roundCurrency(payable)) return { ...amounts, [methodId]: 0 };
  const [holderId] = holder;
  return { ...amounts, [holderId]: 0, [methodId]: roundCurrency(payable) };
}
