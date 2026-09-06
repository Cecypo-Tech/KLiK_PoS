import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  buildSummaryQuery,
  collapseModeRows,
  contextParts,
  exceptionHref,
  exceptionLabel,
  exceptionsCoverMoreThanScope,
  fillHourGaps,
  isExternalHref,
  isScopeComplete,
  readStoredScope,
  shiftStartTime,
  todayIso,
  unmatchedHref,
  writeStoredScope,
  type DashboardSummary,
  type ExceptionRow,
  type ModeRow,
} from "./dashboardSummary";

const mode = (over: Partial<ModeRow> = {}): ModeRow => ({
  mode: "Cash",
  amount: 0,
  later: 0,
  count: 0,
  ...over,
});

const money = (amount: number) => `KES ${amount.toFixed(2)}`;

const summary = (over: Partial<DashboardSummary["scope"]> = {}, identity: Partial<DashboardSummary["identity"]> = {}) =>
  ({
    scope: {
      company: "Dev Co",
      pos_profiles: ["Till 1"],
      available_profiles: ["Till 1", "Till 2"],
      range: "shift",
      date_from: null,
      date_to: null,
      open_shifts: [],
      fallback: null,
      ...over,
    },
    identity: {
      billed: 0,
      billed_gross: 0,
      collected: 0,
      collected_at_sale: 0,
      collected_later: 0,
      credit: 0,
      credit_invoices: 0,
      credit_customers: 0,
      refunds_owed: 0,
      write_off: 0,
      unexplained: 0,
      invoices: 7,
      returns: 0,
      returns_total: 0,
      currency: "KES",
      ...identity,
    },
  }) as DashboardSummary;

describe("buildSummaryQuery", () => {
  it("sends the tills as a JSON list the endpoint can parse", () => {
    const query = buildSummaryQuery({ range: "today", profiles: ["Till 1", "Till 2"] });
    expect(new URLSearchParams(query).get("pos_profiles")).toBe('["Till 1","Till 2"]');
  });

  it("omits the till list entirely when every till is wanted", () => {
    const query = buildSummaryQuery({ range: "today", profiles: [] });
    expect(new URLSearchParams(query).has("pos_profiles")).toBe(false);
  });

  it("carries dates only for a custom range", () => {
    const custom = new URLSearchParams(
      buildSummaryQuery({ range: "custom", profiles: [], dateFrom: "2026-09-01", dateTo: "2026-09-06" })
    );
    expect(custom.get("date_from")).toBe("2026-09-01");

    const week = new URLSearchParams(
      buildSummaryQuery({ range: "week", profiles: [], dateFrom: "2026-09-01", dateTo: "2026-09-06" })
    );
    expect(week.has("date_from")).toBe(false);
  });
});

describe("collapseModeRows", () => {
  it("keeps every mode that moved money", () => {
    const { rows, collapsed } = collapseModeRows([
      mode({ mode: "Cash", amount: 450 }),
      mode({ mode: "Cheque", later: 250 }),
    ]);
    expect(rows.map((r) => r.mode)).toEqual(["Cash", "Cheque"]);
    expect(collapsed).toEqual([]);
  });

  it("collapses the modes that took nothing", () => {
    const { rows, collapsed } = collapseModeRows([
      mode({ mode: "Cash", amount: 450 }),
      mode({ mode: "Card" }),
      mode({ mode: "Bank Draft" }),
    ]);
    expect(rows.map((r) => r.mode)).toEqual(["Cash"]);
    expect(collapsed).toEqual(["Card", "Bank Draft"]);
  });

  it("keeps a zero mode that still has unmatched receipts", () => {
    const { rows, collapsed } = collapseModeRows([
      mode({ mode: "Mpesa-111222", unmatched: 4, unmatched_amount: 12450, shortcode: "600978" }),
    ]);
    expect(rows.map((r) => r.mode)).toEqual(["Mpesa-111222"]);
    expect(collapsed).toEqual([]);
  });

  it("does not collapse a mode that nets to zero after change was given", () => {
    const { rows } = collapseModeRows([mode({ mode: "Cash", amount: -0.5, later: 0.5 })]);
    expect(rows).toEqual([]);
  });
});

describe("exception rows", () => {
  const row = (over: Partial<ExceptionRow> = {}): ExceptionRow => ({
    key: "failed_submissions",
    count: 2,
    link: { route: "/invoice", params: { tab: "queue_failed" } },
    ...over,
  });

  it("reads as a sentence, and counts singulars properly", () => {
    expect(exceptionLabel(row())).toBe("2 sales failed to submit");
    expect(exceptionLabel(row({ count: 1 }))).toBe("1 sale failed to submit");
  });

  it("falls back to the key rather than rendering nothing", () => {
    expect(exceptionLabel(row({ key: "some_new_thing", count: 3 }))).toBe("3 some new thing");
  });

  it("builds the deep link with its filter", () => {
    expect(exceptionHref(row())).toBe("/invoice?tab=queue_failed");
  });

  it("has no href when there is nowhere to send the reader", () => {
    expect(exceptionHref(row({ link: null }))).toBeNull();
  });
});

describe("unmatchedHref", () => {
  it("points at the register, filtered to the shortcode and to what is still pending", () => {
    expect(unmatchedHref(mode({ shortcode: "600978", unmatched: 4 }))).toBe(
      "/app/mpesa-c2b-payment-register?docstatus=0&businessshortcode=600978"
    );
  });

  it("is null when nothing is unmatched", () => {
    expect(unmatchedHref(mode({ shortcode: "600978", unmatched: 0 }))).toBeNull();
  });
});

describe("isExternalHref", () => {
  it("treats a Desk path as a real navigation", () => {
    // navigate() would resolve it under the router basename and render nothing.
    expect(isExternalHref("/app/mpesa-c2b-payment-register?docstatus=0")).toBe(true);
  });

  it("keeps this app's own routes in the router", () => {
    expect(isExternalHref("/invoice?tab=queue_failed")).toBe(false);
  });
});

describe("contextParts", () => {
  it("names the open shifts and when the earliest started", () => {
    const parts = contextParts(
      summary({
        open_shifts: [
          { name: "OPE-2", pos_profile: "Till 2", period_start_date: "2026-09-06 09:30:00" },
          { name: "OPE-1", pos_profile: "Till 1", period_start_date: "2026-09-06 08:02:11" },
        ],
      }),
      money
    );
    expect(parts).toContain("since 08:02, Till 2, Till 1 open");
  });

  it("names a till once even when it has several shifts open", () => {
    const parts = contextParts(
      summary({
        open_shifts: [
          { name: "OPE-1", pos_profile: "Till 1", period_start_date: "2026-09-06 08:02:11" },
          { name: "OPE-2", pos_profile: "Till 1", period_start_date: "2026-09-06 13:24:00" },
          { name: "OPE-3", pos_profile: "Till 1", period_start_date: "2026-09-06 22:52:00" },
        ],
      }),
      money
    );
    expect(parts).toContain("since 08:02, Till 1 open");
  });

  it("says plainly when it fell back to today", () => {
    expect(contextParts(summary({ fallback: "today" }), money)).toContain("no shift open — showing today");
  });

  it("counts credit sales and returns when there are any", () => {
    const parts = contextParts(
      summary({ date_from: "2026-09-06", date_to: "2026-09-06" }, { credit_invoices: 2, returns: 1, returns_total: -100 }),
      money
    );
    expect(parts).toEqual(["7 sales", "2 on credit", "1 return (KES -100.00)", "2026-09-06"]);
  });

  it("stays quiet about credit and returns when there are none", () => {
    expect(contextParts(summary({ date_from: "2026-09-06", date_to: "2026-09-06" }), money)).toEqual([
      "7 sales",
      "2026-09-06",
    ]);
  });
});

describe("shiftStartTime", () => {
  it("is null when no shift reports a start", () => {
    expect(shiftStartTime([{ name: "x", pos_profile: "Till 1", period_start_date: null }])).toBeNull();
  });
});

describe("scope storage", () => {
  // The suite runs in node, so the browser storage the util reaches for is stubbed here.
  // That is also the point: the util must survive a host that has no storage at all.
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };

  beforeEach(() => {
    store.clear();
    (globalThis as unknown as { window: unknown }).window = { localStorage: storage };
  });

  afterEach(() => {
    delete (globalThis as unknown as { window?: unknown }).window;
  });

  it("round-trips the reader's last scope", () => {
    writeStoredScope({ range: "week", profiles: ["Till 1"] });
    expect(readStoredScope()).toEqual({ range: "week", profiles: ["Till 1"] });
  });

  it("survives storage that throws", () => {
    (globalThis as unknown as { window: unknown }).window = {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    };

    expect(readStoredScope()).toBeNull();
    expect(() => writeStoredScope({ range: "today", profiles: [] })).not.toThrow();
  });

  it("survives a corrupt value rather than crashing the page", () => {
    store.set("dashboard-scope", "{not json");
    expect(readStoredScope()).toBeNull();
  });

  it("survives a host with no browser storage at all", () => {
    delete (globalThis as unknown as { window?: unknown }).window;
    expect(readStoredScope()).toBeNull();
    expect(() => writeStoredScope({ range: "today", profiles: [] })).not.toThrow();
  });
});

describe("isScopeComplete", () => {
  it("holds back a half-filled custom range instead of asking the server", () => {
    expect(isScopeComplete({ range: "custom", profiles: [], dateFrom: "2026-09-01" })).toBe(false);
    expect(isScopeComplete({ range: "custom", profiles: [] })).toBe(false);
  });

  it("is satisfied by both ends, and by any other range", () => {
    expect(
      isScopeComplete({ range: "custom", profiles: [], dateFrom: "2026-09-01", dateTo: "2026-09-06" })
    ).toBe(true);
    expect(isScopeComplete({ range: "shift", profiles: [] })).toBe(true);
  });
});

describe("todayIso", () => {
  it("uses the reader's own day, not UTC's", () => {
    // 20:30 on the 6th in a timezone behind UTC is already the 7th in UTC.
    expect(todayIso(new Date(2026, 8, 6, 20, 30))).toBe("2026-09-06");
  });
});

describe("fillHourGaps", () => {
  it("fills the quiet hours between the first and last sale", () => {
    const filled = fillHourGaps([
      { hour: 9, amount: 100, count: 1 },
      { hour: 12, amount: 50, count: 2 },
    ]);
    expect(filled.map((b) => b.hour)).toEqual([9, 10, 11, 12]);
    expect(filled.map((b) => b.amount)).toEqual([100, 0, 0, 50]);
  });

  it("does not invent hours before the first sale or after the last", () => {
    expect(fillHourGaps([{ hour: 14, amount: 10, count: 1 }]).map((b) => b.hour)).toEqual([14]);
  });

  it("stays empty when nothing sold", () => {
    expect(fillHourGaps([])).toEqual([]);
  });
});

describe("exceptionsCoverMoreThanScope", () => {
  const withScope = (profiles: string[], available: string[], exceptions = 1) =>
    ({
      ...summary({ pos_profiles: profiles, available_profiles: available }),
      exceptions: Array.from({ length: exceptions }, () => ({
        key: "failed_submissions",
        count: 1,
        link: null,
      })),
      exceptions_cover_company: true,
    }) as DashboardSummary;

  it("warns when the reader narrowed to some of the tills", () => {
    expect(exceptionsCoverMoreThanScope(withScope(["Till 1"], ["Till 1", "Till 2"]))).toBe(true);
  });

  it("stays quiet when every till is already in scope", () => {
    expect(exceptionsCoverMoreThanScope(withScope([], ["Till 1", "Till 2"]))).toBe(false);
    expect(
      exceptionsCoverMoreThanScope(withScope(["Till 1", "Till 2"], ["Till 1", "Till 2"]))
    ).toBe(false);
  });

  it("stays quiet when there is nothing to report", () => {
    expect(exceptionsCoverMoreThanScope(withScope(["Till 1"], ["Till 1", "Till 2"], 0))).toBe(false);
  });
});
