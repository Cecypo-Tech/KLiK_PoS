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

export const PRICE_POPUP_WIDTH = 224;

export interface PricePopupPosition {
  left: number;
  top?: number;
  bottom?: number;
}

/**
 * Where to pin the (position: fixed) price popup for an anchor rect: below it when the
 * estimated height fits, above it otherwise, and never past the viewport's right edge.
 */
export function computePricePopupPosition(
  anchor: { left: number; top: number; bottom: number },
  optionCount: number,
  viewport: { width: number; height: number }
): PricePopupPosition {
  const estimatedHeight = optionCount * 40 + 16;
  const openBelow = anchor.bottom + estimatedHeight <= viewport.height;
  return {
    left: Math.min(anchor.left, Math.max(8, viewport.width - PRICE_POPUP_WIDTH - 8)),
    ...(openBelow ? { top: anchor.bottom + 6 } : { bottom: viewport.height - anchor.top + 6 }),
  };
}
