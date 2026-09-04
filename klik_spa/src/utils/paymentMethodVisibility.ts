/**
 * Which payment methods get a full row, and which are offered as tags.
 *
 * A POS Profile can carry many modes of payment, and rendering every one as a
 * full row (toggle, icon, name, amount, reference) crowds the checkout. Three
 * get rows; the rest become tags the cashier can promote.
 *
 * Two rules exist to stop rows disappearing from under the cashier mid-sale:
 * a method holding an amount is always a row, and promoted methods are appended
 * rather than sorted into place. A promoted method keeps its appended slot even
 * after it gains an amount - it must not swap places with another promoted row
 * just because the cashier typed into it.
 */

export const VISIBLE_PAYMENT_METHOD_COUNT = 3;

export interface RankedMethod {
  id: string;
  /** Amount tendered against this method. Greater than zero pins it as a row. */
  amount: number;
  /** The POS Profile's default mode. Always a row, wherever it sorts. */
  isDefault: boolean;
  /** Position in the POS Profile's payments table. */
  idx: number;
}

export function partitionPaymentMethods<T extends RankedMethod>(
  methods: T[],
  promotedIds: readonly string[],
  visibleCount: number = VISIBLE_PAYMENT_METHOD_COUNT,
): { rows: T[]; tags: T[] } {
  const sorted = [...methods].sort((a, b) => a.idx - b.idx);

  const head = sorted.slice(0, visibleCount);
  const defaultMethod = sorted.find((method) => method.isDefault);

  // The default earns a slot even when it sorts outside the first `visibleCount`,
  // displacing the last of the head rather than adding a fourth row.
  const base =
    defaultMethod && !head.includes(defaultMethod)
      ? [...sorted.slice(0, Math.max(visibleCount - 1, 0)), defaultMethod].sort((a, b) => a.idx - b.idx)
      : head;

  const baseIds = new Set(base.map((method) => method.id));

  // Promoted methods keep their appended slot regardless of whether they later
  // gain an amount - only base membership excludes a method from the promoted
  // bucket, so a promoted row never gets re-spliced relative to another
  // promoted row when the cashier types into it.
  const promoted = promotedIds
    .map((id) => sorted.find((method) => method.id === id))
    .filter((method): method is T => Boolean(method) && !baseIds.has(method!.id));

  const promotedIdSet = new Set(promoted.map((method) => method.id));

  const active = sorted.filter(
    (method) => !baseIds.has(method.id) && !promotedIdSet.has(method.id) && method.amount > 0,
  );

  const rows = [...base, ...promoted, ...active];
  const rowIds = new Set(rows.map((method) => method.id));

  return { rows, tags: sorted.filter((method) => !rowIds.has(method.id)) };
}
