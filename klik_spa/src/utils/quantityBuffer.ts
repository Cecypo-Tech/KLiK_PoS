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
 * Sentinel meaning "the buffer overflowed". A long barcode must fail safe
 * (Enter then adds 1) rather than truncate to a plausible-looking quantity —
 * and it must STAY failed-safe no matter how many more digits the scanner
 * still has left to type. Resetting to "" on overflow instead of sticking
 * would let a barcode longer than MAX_QUANTITY_DIGITS + 1 cycle back through
 * empty and start building a fresh, plausible-looking (and wrong) quantity
 * from its own tail.
 */
export const OVERFLOW = " ";

/**
 * Append one digit. Returns the buffer unchanged if `digit` is not a single
 * digit. Once the cap is exceeded the buffer becomes OVERFLOW and stays
 * OVERFLOW for every subsequent digit — only a terminator (Enter/+/-/Escape)
 * clears it.
 */
export function appendDigit(buffer: string, digit: string): string {
  if (buffer === OVERFLOW) return OVERFLOW;
  if (!/^[0-9]$/.test(digit)) return buffer;
  if (buffer === "" && digit === "0") return buffer;
  if (buffer.length >= MAX_QUANTITY_DIGITS) return OVERFLOW;
  return buffer + digit;
}

export function deleteDigit(buffer: string): string {
  if (buffer === OVERFLOW) return "";
  return buffer.slice(0, -1);
}

/** An empty buffer means "one", which is what every existing binding already does. */
export function bufferToQuantity(buffer: string): number {
  if (buffer === OVERFLOW) return 1;
  const parsed = Number.parseInt(buffer, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}
