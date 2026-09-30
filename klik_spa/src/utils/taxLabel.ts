/**
 * The tax rate to print on a receipt, and how to word it.
 *
 * The receipt read the rate off `calculations.selectedTax`, which only exists when a
 * Sales Taxes and Charges Template is picked in the POS. When the tax comes from the
 * company's default template instead, that object is undefined and the label rendered
 * as "Tax (% Excl.)" - a percent sign with no number in front of it, on a document
 * handed to a customer.
 *
 * The backend preview already returns the real rates in `tax_breakdown`, so prefer
 * those and fall back to the selected template. When neither knows, say "Tax (Excl.)"
 * rather than printing an empty percentage.
 */

import { roundCurrency } from "./currencyMath";

export interface TaxBreakdownLike {
  rate?: number;
  charge_type?: string;
}

/** Charge types whose rates apply to the same base, so adding them is honest. */
const ADDITIVE_CHARGE_TYPES = new Set(["On Net Total", ""]);

export function getTaxRateForDisplay(
  lines: TaxBreakdownLike[] | undefined,
  fallbackRate?: number | null,
): number | null {
  const charged = (lines || []).filter((line) => Number(line.rate || 0) > 0);

  if (charged.length) {
    // A line that compounds on another row is not additive; rather than print a rate
    // the customer was not charged, print none.
    const additive = charged.every((line) => ADDITIVE_CHARGE_TYPES.has(line.charge_type ?? ""));
    if (!additive) return null;
    return charged.reduce((sum, line) => sum + Number(line.rate || 0), 0);
  }

  const fallback = Number(fallbackRate || 0);
  return fallback > 0 ? fallback : null;
}

export function formatTaxLabel(rate: number | null, isInclusive: boolean): string {
  const suffix = isInclusive ? "Incl." : "Excl.";
  if (rate === null) return `Tax (${suffix})`;
  const shown = rate % 1 === 0 ? rate.toFixed(0) : String(Number(rate.toFixed(2)));
  return `Tax (${shown}% ${suffix})`;
}

/**
 * The tax line of the payment summary and the receipt preview. They read Subtotal (before
 * tax) + Tax = Grand Total for inclusive and exclusive prices alike, so the line names the
 * rate only - "Incl." would suggest the amount is already inside the subtotal above it.
 */
export function formatSummaryTaxLabel(rate: number | null): string {
  if (rate === null) return "Tax";
  const shown = rate % 1 === 0 ? rate.toFixed(0) : String(Number(rate.toFixed(2)));
  return `Tax (${shown}%)`;
}

/**
 * A subtotal before tax. Tax-inclusive prices carry the tax inside them, so it is taken
 * out; with no known rate the figure is left as it is rather than guessed at.
 */
export function exclusiveSubtotal(subtotal: number, isInclusive: boolean, rate: number | null): number {
  if (!isInclusive || !rate) return subtotal;
  return roundCurrency(subtotal - (subtotal * rate) / (100 + rate));
}
