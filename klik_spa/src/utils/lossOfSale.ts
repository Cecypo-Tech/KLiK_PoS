/** Loss of Sale: a line asks for more than is in stock; the till sells what there is and
 * records the rest on the line. Mirrors klik_pos/overrides/loss_of_sale.py - the server's
 * checkout preview is the authority and sends corrections back (LosAdjustment). */

export interface LineSplit {
  quantity: number;
  los_qty: number;
}

export interface PlanInput {
  /** A stock item that may not go negative, with a known balance. */
  limited: boolean;
  available: number;
  requested: number;
  /** What the cart's other lines of this item already take. */
  otherLinesQty: number;
  losEnabled: boolean;
}

export interface LosAdjustment {
  index: number;
  item_code: string;
  quantity: number;
  los_qty: number;
}

const roundQty = (value: number) => Math.round(value * 1e6) / 1e6;

export function splitForLoS(requested: number, availableLeft: number): LineSplit {
  const quantity = Math.max(0, Math.min(requested, availableLeft));
  return { quantity, los_qty: roundQty(requested - quantity) };
}

/** The line's quantity and LoS for a requested amount, or null when the till must refuse it. */
export function planLineQty({ limited, available, requested, otherLinesQty, losEnabled }: PlanInput): LineSplit | null {
  if (!limited) return { quantity: requested, los_qty: 0 };
  const left = Math.max(0, available - otherLinesQty);
  if (requested <= left) return { quantity: requested, los_qty: 0 };
  return losEnabled ? splitForLoS(requested, left) : null;
}

/** The checkout preview's corrections, by position in the request - skipped for a line that is
 * no longer the item the server saw there. */
export function applyLosAdjustments<T extends { id: string; item_code?: string; quantity: number; los_qty?: number }>(
  items: T[],
  adjustments: LosAdjustment[],
): T[] {
  const byIndex = new Map(adjustments.map((adjustment) => [adjustment.index, adjustment]));
  return items.map((item, index) => {
    const adjustment = byIndex.get(index);
    if (!adjustment || (item.item_code || item.id) !== adjustment.item_code) return item;
    return { ...item, quantity: adjustment.quantity, los_qty: adjustment.los_qty };
  });
}

export const losToast = (name: string, uom: string | undefined, split: LineSplit) =>
  `Only ${split.quantity} ${uom || "units"} of ${name} in stock: ${split.los_qty} recorded as Loss of Sale`;
