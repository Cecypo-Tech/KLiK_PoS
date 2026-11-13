import { formatNumber } from "./numberInput";

/** One fact the grid till's side panel shows, as klik_pos.api.item.line_info returns it.
 * Built-ins (in_stock, valuation, ...) carry no value: the panel draws them itself. */
export interface LineInfoRow {
  key: string;
  label: string;
  value?: string;
}

export interface LineInfo {
  rows: LineInfoRow[];
  warehouses: { warehouse: string; qty: number }[];
  uoms: { uom: string; conversion_factor: number }[];
  stock_uom: string;
}

const COST_FACTS = new Set(["valuation", "last_purchase", "margin"]);

/** The facts to draw, in the till's order; the cost ones go when the till hides cost. */
export function visibleFacts(info: LineInfo | null, costHidden: boolean): LineInfoRow[] {
  return (info?.rows ?? []).filter((r) => !(costHidden && COST_FACTS.has(r.key)));
}

/** "1 Box = 24 Nos", one per unit other than the stock unit. */
export function uomLines(info: LineInfo): string[] {
  return info.uoms.map((u) => `1 ${u.uom} = ${formatNumber(u.conversion_factor, "qty")} ${info.stock_uom}`);
}
