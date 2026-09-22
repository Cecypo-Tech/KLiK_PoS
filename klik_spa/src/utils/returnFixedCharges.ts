import type { FixedCharge, ReturnItem } from "../services/returnService";

/** What both return dialogs hold: the picker row, or the single dialog's own state. */
export interface ReturnBasis {
  items: ReturnItem[];
  fixed_charges?: FixedCharge[];
  grand_total: number;
  paid_amount?: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Every quantity still returnable on the invoice is selected, and there is at least one. */
export function everyAvailableQtySelected(invoice: ReturnBasis): boolean {
  const open = invoice.items.filter((item) => item.available_qty > 0);
  return open.length > 0 && open.every((item) => (item.return_qty || 0) >= item.available_qty);
}

/** Whether this fee goes back on the credit note: the cashier's tick, or, until they touch
 * it, the same rule the server applies - the fee comes back only with the whole order. */
export function fixedChargeReturned(charge: FixedCharge, invoice: ReturnBasis): boolean {
  if (charge.reversed_by) return false;
  return charge.return_charge ?? everyAvailableQtySelected(invoice);
}

export function returnsAnyFixedCharge(invoice: ReturnBasis): boolean {
  return (invoice.fixed_charges || []).some((charge) => fixedChargeReturned(charge, invoice));
}

function returnedFixedChargesAmount(invoice: ReturnBasis): number {
  return (invoice.fixed_charges || []).reduce(
    (sum, charge) => sum + (fixedChargeReturned(charge, invoice) ? charge.amount : 0),
    0,
  );
}

function soldFixedChargesAmount(invoice: ReturnBasis): number {
  return (invoice.fixed_charges || []).reduce((sum, charge) => sum + charge.amount, 0);
}

/** Value of what is coming back at the sale's rates: returned items plus any ticked fee. */
export function returnedValue(invoice: ReturnBasis): number {
  const items = invoice.items.reduce((sum, item) => sum + (item.return_qty || 0) * item.rate, 0);
  return round2(items + returnedFixedChargesAmount(invoice));
}

/** Default refund: what the customer paid, scaled by the share of the sale coming back. */
export function refundDefault(invoice: ReturnBasis): number {
  const sold = invoice.items.reduce((sum, item) => sum + item.qty * item.rate, 0) + soldFixedChargesAmount(invoice);
  const share = sold > 0 ? returnedValue(invoice) / sold : 0;
  return round2((invoice.paid_amount || invoice.grand_total) * share);
}
