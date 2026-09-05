/**
 * The quantity buffer behind the POS item list's numeric shortcut.
 *
 * With a product row focused, typing digits builds a quantity that Enter, `+` or
 * `-` then applies. The rules here exist to keep a barcode from being mistaken
 * for a quantity: a wedge scanner types digits and terminates with Enter, so an
 * unbounded buffer would let a scan add thousands of units.
 */

export const MAX_QUANTITY_DIGITS = 4;

/**
 * Append one digit. Returns the buffer unchanged if `digit` is not a single
 * digit, and returns an EMPTY buffer if the cap would be exceeded — a long
 * barcode must fail safe (Enter then adds 1) rather than truncate to a
 * plausible-looking quantity.
 */
export function appendDigit(buffer: string, digit: string): string {
  if (!/^[0-9]$/.test(digit)) return buffer;
  if (buffer === "" && digit === "0") return buffer;
  if (buffer.length >= MAX_QUANTITY_DIGITS) return "";
  return buffer + digit;
}

export function deleteDigit(buffer: string): string {
  return buffer.slice(0, -1);
}

/** An empty buffer means "one", which is what every existing binding already does. */
export function bufferToQuantity(buffer: string): number {
  const parsed = Number.parseInt(buffer, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}
