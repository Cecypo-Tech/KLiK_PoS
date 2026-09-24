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

/**
 * The "Custom Price" field as the cashier types into it. It is seeded with the
 * item's own rate, shown selected the way a focused input selects its contents:
 * the first digit replaces the seed rather than appending to it (opening on 450
 * and typing 9 means 9, not 4509), and Backspace clears it. From then on digits
 * append, one dot is allowed, and a lone leading zero is still "first digit".
 */
export interface CustomPriceDraft {
  value: string;
  selected: boolean;
}

export function seedCustomPrice(rate: number): CustomPriceDraft {
  return { value: String(rate), selected: true };
}

export function typeCustomPrice(draft: CustomPriceDraft, key: string): CustomPriceDraft {
  if (key === "Backspace") {
    return { value: draft.selected ? "" : draft.value.slice(0, -1), selected: false };
  }
  if (!/^[0-9.]$/.test(key)) return draft;
  const base = draft.selected || draft.value === "0" ? "" : draft.value;
  if (key === "." && base.includes(".")) return draft;
  return { value: base + key, selected: false };
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

/** The price list the cart is selling on: the cart's pick, else the customer's, else the profile's. */
export function resolveActivePriceList(
  cartPriceList: string | null | undefined,
  customerPriceList: string | null | undefined,
  profilePriceList: string | null | undefined
): string {
  return cartPriceList || customerPriceList || profilePriceList || "";
}
