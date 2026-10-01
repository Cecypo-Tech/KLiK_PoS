/**
 * Quick entry: one "item, qty, rate" per line, typed or pasted into the POS. The item is
 * matched on the server (klik_pos.api.item.quick_entry.match_items); this reads the lines
 * and decides what goes into the cart and what stays in the box, with a reason.
 */

export interface QuickEntryLine {
  /** 1-based line number in the box, blank lines included. */
  line: number;
  text: string;
  query: string;
  qty: number;
  /** null: use the till's price. */
  rate: number | null;
  error: string | null;
}

export interface MatchResult {
  query: string;
  status: "ok" | "many" | "none" | "template" | "unavailable";
  item: Record<string, unknown> | null;
  candidates: string[];
}

export interface QuickEntryPlan {
  toAdd: Array<{ line: number; item: Record<string, unknown>; qty: number; rate: number | null }>;
  failed: Array<{ line: number; text: string; reason: string }>;
}

const SEPARATOR_LINE = /^[-=_*\s]+$/;

function parseNumber(value: string): number | null {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return null;
  return Number(value);
}

export function parseQuickEntry(text: string): QuickEntryLine[] {
  const lines: QuickEntryLine[] = [];
  text.split(/\r?\n/).forEach((raw, index) => {
    const trimmed = raw.trim();
    if (!trimmed || SEPARATOR_LINE.test(trimmed)) return;
    const [query = "", qtyText = "", rateText = "", ...extra] = trimmed.split(",").map((part) => part.trim());
    const entry: QuickEntryLine = { line: index + 1, text: trimmed, query, qty: 0, rate: null, error: null };
    const qty = parseNumber(qtyText);
    const rate = rateText === "" ? null : parseNumber(rateText);

    if (extra.length) entry.error = "Too many values: enter item, qty, rate";
    else if (!query) entry.error = "Item is missing";
    else if (!qtyText) entry.error = "Quantity is missing";
    else if (qty === null) entry.error = "Quantity must be a number";
    else if (qty <= 0) entry.error = "Quantity must be more than 0";
    else if (rateText !== "" && rate === null) entry.error = "Rate must be a number";
    else if (rate !== null && rate < 0) entry.error = "Rate cannot be negative";

    entry.qty = qty ?? 0;
    entry.rate = rate;
    lines.push(entry);
  });
  return lines;
}

export function failureReason(result: MatchResult): string {
  switch (result.status) {
    case "many":
      return `Several items match "${result.query}": ${result.candidates.join(", ")}`;
    case "template":
      return `${result.candidates[0]} has variants: enter the variant's code`;
    case "unavailable":
      return `${result.candidates[0]} is not available on this till`;
    default:
      return `No item matches "${result.query}"`;
  }
}

/** `results` answers the lines without a parse error, in order. */
export function planQuickEntry(
  lines: QuickEntryLine[],
  results: MatchResult[],
  { allowRateChange }: { allowRateChange: boolean }
): QuickEntryPlan {
  const plan: QuickEntryPlan = { toAdd: [], failed: [] };
  let next = 0;
  for (const entry of lines) {
    if (entry.error) {
      plan.failed.push({ line: entry.line, text: entry.text, reason: entry.error });
      continue;
    }
    const result = results[next++];
    if (!result || result.status !== "ok" || !result.item) {
      plan.failed.push({
        line: entry.line,
        text: entry.text,
        reason: result ? failureReason(result) : `No item matches "${entry.query}"`,
      });
    } else if (entry.rate !== null && !allowRateChange) {
      plan.failed.push({ line: entry.line, text: entry.text, reason: "This till does not allow changing the price" });
    } else {
      plan.toAdd.push({ line: entry.line, item: result.item, qty: entry.qty, rate: entry.rate });
    }
  }
  return plan;
}
