/**
 * Whether a row's date falls between From and To, both inclusive; an empty end is unbounded.
 *
 * Compares the "yyyy-mm-dd" text itself. Parsing it with `new Date()` reads it as UTC
 * midnight, which is the previous day anywhere west of Greenwich.
 */
export function inDateRange(date: string, from: string, to: string): boolean {
  const day = (date || "").slice(0, 10);
  return (!from || day >= from) && (!to || day <= to);
}

/** A remembered From/To value, or "" when it is not a yyyy-mm-dd date. */
export function storedDate(value: unknown): string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "";
}
