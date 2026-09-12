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
