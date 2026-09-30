import { roundCurrency } from "./currencyMath";

/**
 * What the checkout's payment rows hold when it opens.
 *
 * The grand total goes on the till's default mode only when its POS Profile has "Set Grand
 * Total to Default Payment Method" (set_grand_total_to_default_mop) ticked - ERPNext's own
 * rule. Otherwise every row starts empty and the cashier ticks the mode the customer pays in.
 */
export function openingPaymentAmounts(
  modes: Array<{ mode_of_payment: string; default?: number | boolean }>,
  payable: number,
  setGrandTotalToDefaultMop: boolean,
): Record<string, number> {
  if (!setGrandTotalToDefaultMop) return {};
  const defaultMode = modes.find((mode) => Number(mode.default) === 1);
  return defaultMode ? { [defaultMode.mode_of_payment]: roundCurrency(payable) } : {};
}
