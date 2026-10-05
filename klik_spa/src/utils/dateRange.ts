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

/** The local calendar day `offset` days from `now` as "yyyy-mm-dd" (0 = today, -1 = yesterday). */
export function localDay(offset: number, now: Date = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}
