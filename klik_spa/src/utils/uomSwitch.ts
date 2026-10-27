export interface UomMaps {
  uoms: string[];
  prices: Record<string, number>;
  factors: Record<string, number>;
}

/** An item's units, prices and conversion factors, from get_item_uoms_and_prices. */
export function uomMaps(data: {
  base_uom?: string;
  uoms?: { uom: string; conversion_factor: number; price: number }[];
}): UomMaps {
  const rows = Array.isArray(data.uoms) ? data.uoms.filter((row) => row.uom) : [];
  const prices: Record<string, number> = {};
  const factors: Record<string, number> = {};
  for (const row of rows) {
    prices[row.uom] = Number(row.price) || 0;
    factors[row.uom] = Number(row.conversion_factor) || 1;
  }
  if (data.base_uom && !factors[data.base_uom]) factors[data.base_uom] = 1;
  return { uoms: Array.from(new Set(rows.map((row) => row.uom))), prices, factors };
}

/** A cart line moved to another unit. Its `available` is kept in the line's unit (the
 * listing gives it so), so it is converted with the line: 100 rolls become 1,500 kg. */
export function lineInUom<T extends { available?: number; conversion_factor?: number }>(
  line: T,
  uom: string,
  price: number,
  conversionFactor?: number,
): T & { uom: string; price: number } {
  if (!conversionFactor) return { ...line, uom, price };
  const from = Number(line.conversion_factor) > 0 ? Number(line.conversion_factor) : 1;
  const available =
    typeof line.available === "number" ? Math.round((line.available * from) / conversionFactor * 1e6) / 1e6 : line.available;
  return { ...line, uom, price, conversion_factor: conversionFactor, available };
}

/** The unit after `current`, wrapping round; null when there is only one. */
export function nextUom(uoms: string[], current: string | undefined): string | null {
  if (uoms.length < 2) return null;
  return uoms[(uoms.indexOf(current ?? "") + 1) % uoms.length];
}

/** Price and factor for a line moving to `toUom`: the unit's own price, else the current
 * price converted through the stock unit. */
export function switchUom({ prices, factors }: Pick<UomMaps, "prices" | "factors">, fromUom: string, fromPrice: number, toUom: string) {
  const fromFactor = factors[fromUom] || 1;
  const conversionFactor = factors[toUom] || 1;
  const direct = prices[toUom];
  const price = direct > 0 ? direct : (fromPrice / fromFactor) * conversionFactor;
  return { uom: toUom, price: Number(price.toFixed(6)), conversionFactor };
}

/** The UOM field's label: carries the conversion factor when the line is not in the stock unit. */
export function uomLabel(selectedUom: string, stockUom: string, factor: number) {
  if (!selectedUom || !stockUom || selectedUom === stockUom) return "UOM";
  const formatted = new Intl.NumberFormat(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 4 }).format(factor);
  return `UOM - Factor ${formatted}`;
}
