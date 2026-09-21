export interface PriceOption {
  label: string;
  rate: number;
  isCustom?: boolean;
}

/**
 * Options for the item-list '*' price popup: one per price list the item has a
 * rate on, plus a trailing editable "Custom Price" option when the POS Profile
 * allows rate changes. fallbackRate seeds the custom option's starting value
 * (the item's own default rate) before the cashier types over it.
 */
export function buildPriceOptions(
  priceLists: { price_list: string; rate: number }[],
  allowRateChange: boolean,
  fallbackRate: number
): PriceOption[] {
  const options: PriceOption[] = priceLists.map((p) => ({ label: p.price_list, rate: p.rate }));
  if (allowRateChange) {
    options.push({ label: "Custom Price", rate: fallbackRate, isCustom: true });
  }
  return options;
}

/** Wraps in both directions; returns 0 for an empty list instead of NaN. */
export function cyclePriceOptionIndex(current: number, length: number, direction: 1 | -1): number {
  if (length <= 0) return 0;
  return (current + direction + length) % length;
}
