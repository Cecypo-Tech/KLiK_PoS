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

/**
 * What a cart line's price chip shows. A line sells on the cart's price list until it is
 * switched to another (selected) or given a price of its own (customRate). A price of its own
 * that is not the switched-to list's - typed with '*', quick entry's '@', or in the Rate
 * field - shows as custom: naming a list beside a rate it does not sell at misleads.
 */
export function linePriceShown<T extends { price_list: string; rate: number }>(
  lists: T[],
  selected: string | undefined,
  customRate: number | null | undefined,
  cartList: string
): { entry: T | undefined; active: T | undefined; customRate: number | null } {
  const priced = typeof customRate === "number" && Number.isFinite(customRate);
  const active = lists.find(
    (list) => list.price_list === selected && (!priced || Number(list.rate) === customRate)
  );
  if (priced && !active) return { entry: undefined, active: undefined, customRate: customRate as number };
  return { entry: active || lists.find((list) => list.price_list === cartList), active, customRate: null };
}

/** The Rate box's '*': the price popup, but only as the first key (the box empty or all
 * selected). Inside a sum, '*' is multiply ("4*5"), and a sum never starts with one. */
export function starOpensPricePopup(key: string, value: string, selectionStart: number | null, selectionEnd: number | null): boolean {
  return key === "*" && (value === "" || (selectionStart === 0 && selectionEnd === value.length));
}

export interface PricePopupState {
  options: PriceOption[];
  selectedIndex: number;
  customValue: string;
  customSelected: boolean;
}

/** The popup over a line's Rate: its price lists (+ Custom when rates may change), on the active list. */
export function openPricePopupState(
  priceLists: { price_list: string; rate: number }[],
  allowRateChange: boolean,
  currentRate: number,
  activeList?: string,
): PricePopupState {
  const options = buildPriceOptions(priceLists, allowRateChange, currentRate);
  const seed = seedCustomPrice(currentRate);
  return {
    options,
    selectedIndex: Math.max(0, [priceLists.findIndex((p) => p.price_list === activeList), priceLists.findIndex((p) => Number(p.rate) === currentRate)].find((i) => i >= 0) ?? 0),
    customValue: seed.value,
    customSelected: seed.selected,
  };
}

export type PricePopupPick = { priceList: string; rate: number } | { rate: number };

/** One key while the popup is open. `handled: false` lets the key carry on (Tab moves focus). */
export function pricePopupKey(
  s: PricePopupState,
  key: string,
): { state: PricePopupState | null; pick?: PricePopupPick; handled: boolean } {
  const current = s.options[s.selectedIndex];
  const customIndex = s.options.findIndex((o) => o.isCustom);
  if (key === "ArrowDown" || key === "ArrowUp") {
    const selectedIndex = cyclePriceOptionIndex(s.selectedIndex, s.options.length, key === "ArrowDown" ? 1 : -1);
    const option = s.options[selectedIndex];
    const seed = option?.isCustom ? seedCustomPrice(option.rate) : null;
    return { state: { ...s, selectedIndex, ...(seed ? { customValue: seed.value, customSelected: seed.selected } : {}) }, handled: true };
  }
  if (key === "Escape") return { state: null, handled: true };
  if (key === "Tab") return { state: null, handled: false };
  if (key === "Enter") {
    if (!current) return { state: null, handled: true };
    if (!current.isCustom) return { state: null, pick: { priceList: current.label, rate: current.rate }, handled: true };
    const rate = parseFloat(s.customValue);
    // Empty or 0 is "no price set", not free: the line keeps its rate.
    return Number.isFinite(rate) && rate > 0 ? { state: null, pick: { rate }, handled: true } : { state: null, handled: true };
  }
  if ((/^[0-9.]$/.test(key) || key === "Backspace") && customIndex >= 0) {
    // Typing starts a custom price from any row: the first digit replaces the seed.
    const base = current?.isCustom ? s : { ...s, customValue: seedCustomPrice(s.options[customIndex]!.rate).value, customSelected: true };
    const draft = typeCustomPrice({ value: base.customValue, selected: base.customSelected }, key);
    return { state: { ...s, selectedIndex: customIndex, customValue: draft.value, customSelected: draft.selected }, handled: true };
  }
  return { state: s, handled: true }; // swallowed: the popup is modal while open
}
