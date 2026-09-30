import { roundCurrency } from "./currencyMath";

export interface SummaryInput {
  /** The server's net_total: before tax, and after the order discount's pre-tax share. */
  netTotal: number;
  /** total_taxes_and_charges, which includes any shipping row. */
  taxTotal: number;
  grandTotal: number;
  /** The order discount as entered, applied on the grand total. */
  discount: number;
  shipping: number;
}

/**
 * The payment summary's Subtotal, Discount and Tax, all before tax so that
 * Subtotal - Discount + Tax (+ Shipping) = Grand Total.
 *
 * ERPNext spreads an order discount over the lines in proportion, so its pre-tax share is
 * the entered amount scaled by net / (grand - shipping); the subtotal before the discount
 * is net_total plus that share, and the discount is what balances the rows to the total.
 */
export function summaryFigures(p: SummaryInput): { subtotal: number; discount: number; tax: number } {
  const tax = roundCurrency(Math.max(0, p.taxTotal - p.shipping));
  const taxedBase = p.grandTotal - p.shipping;
  if (!(p.discount > 0 && taxedBase > 0)) return { subtotal: roundCurrency(p.netTotal), discount: 0, tax };
  const subtotal = roundCurrency(p.netTotal + (p.discount * p.netTotal) / taxedBase);
  // The discount balances the rows: ERPNext's own net + taxes can sit a cent off its grand
  // total once a discount is spread over the lines, and the summary must add up exactly.
  const discount = roundCurrency(subtotal + tax + p.shipping - p.grandTotal);
  return { subtotal, discount, tax };
}
