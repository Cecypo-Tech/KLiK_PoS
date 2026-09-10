/**
 * What the opening screen offers, and what it insists on.
 *
 * A till opens where it last closed. ERPNext carries nothing forward, so the field used to
 * start at zero every morning and whatever was typed became the figure the shift was
 * judged against - and a figure typed low hides a shortfall, because the count at close
 * still reconciles. So: suggest the last closing, and ask for a reason before accepting
 * anything else.
 *
 * Only cash carries a float. Card, bank and M-Pesa money goes straight to its account, and
 * that account's balance is not a cashier's business, so those modes open at zero and are
 * not editable here. The server enforces all of this again on the document.
 */

export interface OpeningSuggestionMode {
  mode_of_payment: string;
  type: string;
  carries_float: boolean;
  suggested_amount: number;
  previous_closing_amount: number;
  previous_closing_entry: string | null;
  previous_closed_on: string | null;
}

export interface OpeningSuggestion {
  pos_profile: string;
  modes: OpeningSuggestionMode[];
}

export interface OpeningRow {
  mode_of_payment: string;
  type: string;
  carriesFloat: boolean;
  amount: number;
  previousClosing: number;
  /** Whether this till has a closing to be measured against at all. */
  hasHistory: boolean;
  closedOn: string | null;
  reason: string;
}

export interface ProfileMode {
  mode_of_payment: string;
  type?: string;
  default?: number;
}

/** The rows the dialog starts with: profile modes, filled in from the suggestion. */
export function buildOpeningRows(
  modes: ProfileMode[],
  suggestion?: OpeningSuggestion | null,
): OpeningRow[] {
  const byMode = new Map<string, OpeningSuggestionMode>();
  for (const mode of suggestion?.modes ?? []) {
    byMode.set(mode.mode_of_payment, mode);
  }

  return modes
    .filter((mode) => !!mode.mode_of_payment)
    .map((mode) => {
      const hint = byMode.get(mode.mode_of_payment);
      const carriesFloat = hint ? hint.carries_float : (mode.type ?? "General") === "Cash";
      return {
        mode_of_payment: mode.mode_of_payment,
        type: hint?.type ?? mode.type ?? "General",
        carriesFloat,
        amount: carriesFloat ? (hint?.suggested_amount ?? 0) : 0,
        previousClosing: carriesFloat ? (hint?.previous_closing_amount ?? 0) : 0,
        hasHistory: carriesFloat && !!hint?.previous_closing_entry,
        closedOn: hint?.previous_closed_on ?? null,
        reason: "",
      };
    });
}

export function setAmount(rows: OpeningRow[], index: number, amount: number): OpeningRow[] {
  return rows.map((row, i) =>
    // A mode with no float stays at zero however the input is driven.
    i === index && row.carriesFloat ? { ...row, amount: Number.isFinite(amount) ? amount : 0 } : row,
  );
}

export function setReason(rows: OpeningRow[], index: number, reason: string): OpeningRow[] {
  return rows.map((row, i) => (i === index ? { ...row, reason } : row));
}

/** How far this row's opening sits from what the till last counted. */
export function variance(row: OpeningRow): number {
  if (!row.hasHistory) return 0;
  return round(row.amount - row.previousClosing);
}

export function needsReason(row: OpeningRow): boolean {
  return variance(row) !== 0 && !row.reason.trim();
}

/** Rows that must be explained before the shift can be opened. */
export function unexplained(rows: OpeningRow[]): OpeningRow[] {
  return rows.filter(needsReason);
}

export function canOpen(rows: OpeningRow[]): boolean {
  return rows.length > 0 && unexplained(rows).length === 0;
}

export function totalFloat(rows: OpeningRow[]): number {
  return round(rows.reduce((sum, row) => sum + (row.carriesFloat ? row.amount : 0), 0));
}

export function toPayload(
  rows: OpeningRow[],
): { mode_of_payment: string; opening_amount: number; variance_reason?: string }[] {
  return rows.map((row) => {
    const amount = row.carriesFloat ? row.amount || 0 : 0;
    const reason = row.reason.trim();
    return reason && variance(row) !== 0
      ? { mode_of_payment: row.mode_of_payment, opening_amount: amount, variance_reason: reason }
      : { mode_of_payment: row.mode_of_payment, opening_amount: amount };
  });
}

/** Currency, not physics: two decimals is the most a drawer can hold. */
function round(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}
