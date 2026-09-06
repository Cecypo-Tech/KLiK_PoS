/**
 * The shapes and the pure logic behind the Sales Dashboard.
 *
 * Everything here is a function of the server's answer alone: the page does no arithmetic
 * on money. The old dashboard summed invoices in the browser and showed percentages of a
 * total it had computed differently from the headline figure, so the two could not agree —
 * this module is deliberately incapable of that, and the components below it only lay out
 * what `get_dashboard_summary` already balanced.
 */

export type RangeKey = "shift" | "today" | "week" | "month" | "custom";

export interface OpenShift {
  name: string;
  pos_profile: string;
  period_start_date: string | null;
}

export interface DashboardScope {
  company: string;
  pos_profiles: string[];
  available_profiles: string[];
  range: RangeKey;
  date_from: string | null;
  date_to: string | null;
  open_shifts: OpenShift[];
  /** Set to "today" when a shift was asked for and none is open. */
  fallback: string | null;
}

export interface DashboardIdentity {
  billed: number;
  billed_gross: number;
  collected: number;
  collected_at_sale: number;
  collected_later: number;
  credit: number;
  credit_invoices: number;
  credit_customers: number;
  refunds_owed: number;
  write_off: number;
  unexplained: number;
  invoices: number;
  returns: number;
  returns_total: number;
  currency: string;
}

export interface ModeRow {
  mode: string;
  amount: number;
  later: number;
  count: number;
  shortcode?: string;
  unmatched?: number;
  unmatched_amount?: number;
}

export interface ExceptionRow {
  key: string;
  count: number;
  amount?: number;
  shortcodes?: string[];
  link: { route: string; params: Record<string, string> } | null;
}

export interface DashboardPerformance {
  kpis: { revenue: number; invoices: number; average: number; items: number };
  hourly: Array<{ hour: number; amount: number; count: number }>;
  top_items: Array<{ item_code: string; item_name: string; amount: number; qty: number }>;
  cashiers: Array<{ cashier: string; amount: number; count: number }>;
  recent: Array<{
    name: string;
    customer_name: string;
    amount: number;
    is_return: boolean;
    time: string;
    status: string;
    mode_of_payment: string;
  }>;
}

export interface DashboardSummary {
  scope: DashboardScope;
  identity: DashboardIdentity;
  collected_by_mode: ModeRow[];
  exceptions: ExceptionRow[];
  /** Exceptions are counted for the whole company, not only the tills in scope. */
  exceptions_cover_company: boolean;
  performance: DashboardPerformance;
}

export interface ScopeRequest {
  range: RangeKey;
  profiles: string[];
  dateFrom?: string;
  dateTo?: string;
  company?: string;
}

export const SCOPE_STORAGE_KEY = "dashboard-scope";

export const RANGE_LABELS: Record<RangeKey, string> = {
  shift: "Shift",
  today: "Today",
  week: "Week",
  month: "Month",
  custom: "Dates",
};

/** Query string for get_dashboard_summary. Empty values are omitted, never sent blank. */
export function buildSummaryQuery(request: ScopeRequest): string {
  const params = new URLSearchParams();
  params.set("range", request.range);
  if (request.company) params.set("company", request.company);
  if (request.profiles.length > 0) params.set("pos_profiles", JSON.stringify(request.profiles));
  if (request.range === "custom") {
    if (request.dateFrom) params.set("date_from", request.dateFrom);
    if (request.dateTo) params.set("date_to", request.dateTo);
  }
  return params.toString();
}

/**
 * Whether this scope can be asked for yet.
 *
 * A custom range with one end missing is not an error the reader made; it is a half-filled
 * form. Asking anyway returns "A custom range needs both date_from and date_to", which is
 * the server explaining itself to the wrong audience.
 */
export function isScopeComplete(request: ScopeRequest): boolean {
  return request.range !== "custom" || Boolean(request.dateFrom && request.dateTo);
}

/** Today, in the reader's own timezone rather than UTC. */
export function todayIso(now: Date = new Date()): string {
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/**
 * Modes that took no money collapse into one line.
 *
 * A mode with unmatched M-Pesa receipts keeps its own row even at zero: the badge is the
 * only way into the register for that shortcode, and collapsing it would hide money that
 * has arrived and belongs to nobody yet.
 */
export function collapseModeRows(rows: ModeRow[]): { rows: ModeRow[]; collapsed: string[] } {
  const visible: ModeRow[] = [];
  const collapsed: string[] = [];

  rows.forEach((row) => {
    const moved = row.amount + row.later !== 0;
    if (moved || (row.unmatched ?? 0) > 0) {
      visible.push(row);
    } else {
      collapsed.push(row.mode);
    }
  });

  return { rows: visible, collapsed };
}

const EXCEPTION_LABELS: Record<string, (count: number) => string> = {
  failed_submissions: (n) => `${n} sale${n === 1 ? "" : "s"} failed to submit`,
  queued_submissions: (n) => `${n} sale${n === 1 ? "" : "s"} still queued`,
  stale_held_orders: (n) => `${n} held order${n === 1 ? "" : "s"} left open`,
  shifts_open_past_today: (n) => `${n} shift${n === 1 ? "" : "s"} open from a previous day`,
  unmatched_mpesa_unmapped: (n) => `${n} M-Pesa receipt${n === 1 ? "" : "s"} not matched to a sale`,
};

export function exceptionLabel(row: ExceptionRow): string {
  const label = EXCEPTION_LABELS[row.key];
  return label ? label(row.count) : `${row.count} ${row.key.replace(/_/g, " ")}`;
}

/** Where an exception row leads. Null means there is nowhere useful to send the reader. */
export function exceptionHref(row: ExceptionRow): string | null {
  if (!row.link) return null;
  const params = new URLSearchParams(row.link.params || {});
  const query = params.toString();
  return query ? `${row.link.route}?${query}` : row.link.route;
}

export const MPESA_REGISTER_ROUTE = "/app/mpesa-c2b-payment-register";

/**
 * The M-Pesa register, filtered to the shortcode whose receipts are unmatched.
 * It lives in the Desk, not in this app - see isExternalHref.
 */
export function unmatchedHref(row: ModeRow): string | null {
  if (!row.shortcode || !(row.unmatched ?? 0)) return null;
  const params = new URLSearchParams({ docstatus: "0", businessshortcode: row.shortcode });
  return `${MPESA_REGISTER_ROUTE}?${params.toString()}`;
}

/**
 * Whether following this link means leaving the SPA.
 *
 * The router is mounted under /klik_pos, so handing a Desk path to navigate() produces
 * /klik_pos/app/... and a blank page. These have to be a real navigation.
 */
export function isExternalHref(href: string): boolean {
  return href.startsWith("/app") || /^https?:\/\//.test(href);
}

/**
 * The line under the hero figures: what those numbers are made of, and what they cover.
 * Money is formatted by the caller so this stays free of currency knowledge.
 */
export function contextParts(
  summary: DashboardSummary,
  formatMoney: (amount: number) => string
): string[] {
  const { identity, scope } = summary;
  const parts: string[] = [`${identity.invoices} sale${identity.invoices === 1 ? "" : "s"}`];

  if (identity.credit_invoices > 0) {
    parts.push(`${identity.credit_invoices} on credit`);
  }
  if (identity.returns > 0) {
    parts.push(
      `${identity.returns} return${identity.returns === 1 ? "" : "s"} (${formatMoney(identity.returns_total)})`
    );
  }

  if (scope.open_shifts.length > 0) {
    const since = shiftStartTime(scope.open_shifts);
    // One till can have several shifts open at once (dev had three on one profile), and
    // naming it once per shift read as three tills that do not exist.
    const tills = [...new Set(scope.open_shifts.map((shift) => shift.pos_profile))].join(", ");
    parts.push(since ? `since ${since}, ${tills} open` : `${tills} open`);
  } else if (scope.fallback === "today") {
    parts.push("no shift open — showing today");
  } else if (scope.date_from && scope.date_to) {
    parts.push(scope.date_from === scope.date_to ? scope.date_from : `${scope.date_from} to ${scope.date_to}`);
  }

  return parts;
}

/**
 * A continuous run of hours from the first sale to the last, zeroes included.
 *
 * The server returns only the hours that took money. Rendered directly, five busy hours
 * become five blocks each a fifth of the width, which reads as five equal periods rather
 * than as a trading day with quiet stretches in it.
 */
export function fillHourGaps(
  hourly: Array<{ hour: number; amount: number; count: number }>
): Array<{ hour: number; amount: number; count: number }> {
  if (hourly.length === 0) return [];

  const byHour = new Map(hourly.map((bucket) => [bucket.hour, bucket]));
  const hours = hourly.map((bucket) => bucket.hour);
  const first = Math.min(...hours);
  const last = Math.max(...hours);

  const filled = [];
  for (let hour = first; hour <= last; hour++) {
    filled.push(byHour.get(hour) ?? { hour, amount: 0, count: 0 });
  }
  return filled;
}

/**
 * Whether the exception strip is reporting on more tills than the reader selected.
 *
 * The money answers for the chosen tills; the exceptions answer for the shop, so that work
 * stranded on a renamed or deleted till cannot hide. Where the two differ the strip has to
 * say so, or a manager looking at one till reads another till's failures as their own.
 */
export function exceptionsCoverMoreThanScope(summary: DashboardSummary): boolean {
  const { scope } = summary;
  if (!summary.exceptions_cover_company || summary.exceptions.length === 0) return false;
  const selected = scope.pos_profiles.length;
  return selected > 0 && selected < scope.available_profiles.length;
}

/** The earliest start among the open shifts, as HH:MM. */
export function shiftStartTime(shifts: OpenShift[]): string | null {
  const starts = shifts
    .map((shift) => shift.period_start_date)
    .filter((value): value is string => Boolean(value))
    .sort();
  if (starts.length === 0) return null;
  const match = starts[0]?.match(/(\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : null;
}

/** The reader's last scope, or null. Storage can throw outright in a locked-down browser. */
export function readStoredScope(): Partial<ScopeRequest> | null {
  try {
    const raw = window.localStorage.getItem(SCOPE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as Partial<ScopeRequest>;
  } catch {
    return null;
  }
}

export function writeStoredScope(scope: ScopeRequest): void {
  try {
    window.localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify(scope));
  } catch {
    // A remembered filter is a convenience; losing it must never break the page.
  }
}
