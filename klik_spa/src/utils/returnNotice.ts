/**
 * What the single-invoice return dialog should say below its item table.
 *
 * A load failure (the till refusing the invoice, the network) is reported as such.
 * "All returned" is claimed only for rows that actually loaded and have nothing left:
 * an empty list used to satisfy "every row is zero", so a refused invoice read as
 * "already returned" and sent people looking for a credit note that did not exist.
 */
export type ReturnNotice = "load-error" | "all-returned" | null;

export function returnNotice(items: ReadonlyArray<{ available_qty: number }>, loadError: string | null): ReturnNotice {
  if (loadError) return "load-error";
  if (items.length > 0 && items.every((item) => item.available_qty === 0)) return "all-returned";
  return null;
}
