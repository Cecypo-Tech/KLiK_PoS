/**
 * Whether a row passes Invoice History's payment filter.
 *
 * A held order has no payment yet, so the filter never hides one: the filter is remembered
 * per browser, and a cashier who once filtered sales by Cash came back to an empty Held tab.
 */
export function matchesPaymentFilter(
  row: { paymentMethod?: string; isHeldOrder?: boolean },
  paymentFilter: string,
): boolean {
  return paymentFilter === "all" || !!row.isHeldOrder || row.paymentMethod === paymentFilter;
}
