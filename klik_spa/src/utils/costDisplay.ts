import { getDisplayCost, getInclusiveTaxRate } from "./costMargin";

/** POS Profile "Cost Display": which cost the till shows and works margin from. */
export type CostMode = "Hidden" | "Valuation" | "Last Purchase Cost";

export function costMode(posDetails: { custom_cost_display?: unknown } | null | undefined): CostMode {
  const mode = posDetails?.custom_cost_display;
  return mode === "Valuation" || mode === "Last Purchase Cost" ? mode : "Hidden";
}

/** The cost to show, and the other one with its label for the hover. */
export function pickCost(mode: CostMode, valuation: number | null | undefined, lastPurchase: number | null | undefined) {
  const val = Number(valuation) || 0;
  const last = Number(lastPurchase) || 0;
  return mode === "Last Purchase Cost"
    ? { shown: last, other: val, otherLabel: "Valuation" }
    : { shown: val, other: last, otherLabel: "Last purchase" };
}

interface CostedItem {
  cost_price?: number;
  last_purchase_cost?: number;
  last_purchase_date?: string | null;
  tax_info?: Parameters<typeof getInclusiveTaxRate>[0];
}

/** A list or dropdown cost cell: the chosen cost as shown beside a VAT-inclusive rate, and the
 * other cost for its hover. Both figures are per the listed UOM. */
export function itemCostCell(item: CostedItem, mode: CostMode, fmt: (amount: number) => string) {
  const vat = getInclusiveTaxRate(item.tax_info);
  const { shown, other, otherLabel } = pickCost(mode, item.cost_price, item.last_purchase_cost);
  const shownCost = getDisplayCost(shown, vat);
  let otherText = other > 0 ? fmt(getDisplayCost(other, vat)) : "none";
  if (otherLabel === "Last purchase") {
    otherText = other > 0 && item.last_purchase_date ? `${otherText} on ${item.last_purchase_date}` : other > 0 ? otherText : "no purchase invoice";
  }
  return {
    text: shownCost > 0 ? fmt(shownCost) : "—",
    title: `${otherLabel}: ${otherText}${vat > 0 ? ` (costs incl. ${vat}% VAT)` : ""}`,
  };
}
