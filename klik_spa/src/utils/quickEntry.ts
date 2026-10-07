/**
 * Quick entry: an order pasted into the POS. The server reads and matches every line
 * (klik_pos.api.item.quick_entry.resolve_lines); this decides which lines are ready for the
 * cart and which the cashier must look at first. Nothing is added until every line is ready
 * or skipped.
 */

export type LineStatus = "ok" | "many" | "conflict" | "none" | "template" | "unavailable" | "invalid";

export interface ResolvedLine {
  text: string;
  status: LineStatus;
  qty: number;
  /** The line had more than one number that could be the quantity: qty is a guess. */
  qty_ambiguous: boolean;
  /** null: the till's price. */
  rate: number | null;
  /** Cart-ready, tax details included; null unless status is ok. */
  item: Record<string, unknown> | null;
  candidates: Array<{ code: string; name: string }>;
  reason: string | null;
}

export interface ReviewRow extends ResolvedLine {
  /** 1-based line number in the box, blank lines included. */
  line: number;
  skip: boolean;
}

export interface ReviewContext {
  allowRateChange: boolean;
  isOutOfStock: (item: Record<string, unknown>) => boolean;
}

export interface AddEntry {
  line: number;
  item: Record<string, unknown>;
  qty: number;
  rate: number | null;
}

/** Same as the server's cap (klik_pos.api.item.quick_entry.MAX_LINES). */
export const MAX_LINES = 500;
const SEPARATOR_LINE = /^[-=_*\s]+$/;

export function splitLines(text: string): Array<{ line: number; text: string }> {
  return text
    .split(/\r?\n/)
    .map((raw, index) => ({ line: index + 1, text: raw.trim() }))
    .filter(({ text }) => text && !SEPARATOR_LINE.test(text));
}

export function toRows(lines: Array<{ line: number; text: string }>, answers: ResolvedLine[]): ReviewRow[] {
  return lines.map(({ line }, index) => ({ ...(answers[index] as ResolvedLine), line, skip: false }));
}

/** Why a row cannot go into the cart as it stands, or null when it can. */
export function rowProblem(row: ReviewRow, ctx: ReviewContext): string | null {
  if (row.status !== "ok" || !row.item) return row.reason ?? `No item matches "${row.text}"`;
  if (!(row.qty > 0)) return "Quantity must be more than 0";
  if (row.qty_ambiguous) return "Check the quantity: the line has more than one number";
  if (row.rate !== null && !ctx.allowRateChange) return "This till does not allow changing the price";
  if (ctx.isOutOfStock(row.item)) return `${String(row.item.id)} is out of stock`;
  return null;
}

/** The review's order: lines that need a look on top, so a long paste does not hide them. Set
 * once when the review opens - a row the cashier fixes stays where it is. */
export function problemsFirst(rows: ReviewRow[], ctx: ReviewContext): ReviewRow[] {
  const flagged = rows.filter((row) => rowProblem(row, ctx) !== null);
  return [...flagged, ...rows.filter((row) => !flagged.includes(row))];
}

export function reviewOutcome(rows: ReviewRow[], ctx: ReviewContext) {
  const toAdd: AddEntry[] = [];
  const skipped: ReviewRow[] = [];
  const blocked: ReviewRow[] = [];
  for (const row of rows) {
    if (row.skip) skipped.push(row);
    else if (rowProblem(row, ctx)) blocked.push(row);
    else toAdd.push({ line: row.line, item: row.item as Record<string, unknown>, qty: row.qty, rate: row.rate });
  }
  return { toAdd, skipped, blocked };
}

/** The row re-matched (a candidate picked, a code typed): the new item, the row's own qty and rate. */
export function withMatch(row: ReviewRow, match: ResolvedLine): ReviewRow {
  return { ...row, status: match.status, item: match.item, candidates: match.candidates, reason: match.reason, skip: false };
}
