/**
 * Total net weight of a cart, the same number ERPNext writes to `total_net_weight`.
 *
 * An Item's `weight_per_unit` is per stock UOM, so a line sold in another UOM is
 * `quantity x conversion_factor` stock units. Lines without a weight contribute nothing.
 */

export interface WeighableLine {
  quantity?: number;
  conversion_factor?: number;
  weight_per_unit?: number;
  weight_uom?: string;
}

export interface CartWeight {
  total: number;
  /** The weight UOM when every weighed line agrees; empty when none or mixed. */
  uom: string;
  mixedUoms: boolean;
}

export function getCartNetWeight(lines: WeighableLine[]): CartWeight {
  let total = 0;
  const uoms = new Set<string>();

  for (const line of lines) {
    const perUnit = Number(line.weight_per_unit || 0);
    const qty = Number(line.quantity || 0);
    if (perUnit <= 0 || qty <= 0) continue;

    const factor = Number(line.conversion_factor || 0) || 1;
    total += qty * factor * perUnit;
    if (line.weight_uom) uoms.add(line.weight_uom);
  }

  const rounded = Math.round(total * 1000) / 1000;
  return {
    total: rounded,
    uom: uoms.size === 1 ? ([...uoms][0] ?? "") : "",
    mixedUoms: uoms.size > 1,
  };
}

export function formatCartWeight(weight: CartWeight): string {
  const value = weight.total.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return weight.uom ? `${value} ${weight.uom}` : value;
}
