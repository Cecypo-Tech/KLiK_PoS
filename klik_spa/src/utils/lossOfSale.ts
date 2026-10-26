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
  /** In stock units. */
  available: number;
  /** In the line's unit. */
  requested: number;
  /** What the cart's other lines of this item already take, in stock units (linesStockQty). */
  otherLinesQty: number;
  losEnabled: boolean;
  /** Stock units per one of the line's unit, e.g. 1/15 for kg of a wire stocked in 15 kg rolls. */
  factor?: number;
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
export function planLineQty({ limited, available, requested, otherLinesQty, losEnabled, factor }: PlanInput): LineSplit | null {
  if (!limited) return { quantity: requested, los_qty: 0 };
  const left = roundQty(Math.max(0, available - otherLinesQty) / stockFactor({ conversion_factor: factor }));
  if (requested <= left) return { quantity: requested, los_qty: 0 };
  return losEnabled ? splitForLoS(requested, left) : null;
}

/** Stock units in one of the line's unit; 1 when the line has no factor. */
export const stockFactor = (line: { conversion_factor?: number }) =>
  Number(line.conversion_factor) > 0 ? Number(line.conversion_factor) : 1;

/** Stock units the cart's lines of one item hold (but `exceptId`), each line in its own unit. */
export const linesStockQty = (
  lines: { id: string; item_code?: string; quantity: number; conversion_factor?: number }[],
  code: string,
  exceptId?: string,
) =>
  lines
    .filter((line) => line.id !== exceptId && (line.item_code || line.id) === code)
    .reduce((sum, line) => sum + line.quantity * stockFactor(line), 0);

/** The refusal for a request stock cannot cover, in the line's unit. */
export const noStockMessage = (name: string, uom: string | undefined, stockAvailable: number, factor?: number) =>
  `Only ${(stockAvailable / stockFactor({ conversion_factor: factor })).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${uom || "units"} of ${name} available`;

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

/** What a qty box sends on blur: nothing unless it was typed in since focus. Left untouched it
 * would report the line's own quantity, which the store reads as a fresh request - dropping the
 * line's Loss of Sale (or deleting a 0-qty LoS line). Retyped, even to the same number, it is a
 * request: on 10 + LoS 6, typing 10 means "just the 10". */
export const qtyToSend = (edited: boolean, typed: number): number | null => (edited ? typed : null);

export const losToast = (name: string, uom: string | undefined, split: LineSplit) =>
  `Only ${split.quantity} ${uom || "units"} of ${name} in stock: ${split.los_qty} recorded as Loss of Sale`;
