import { describe, expect, it } from "vitest";
import {
  buildOpeningRows,
  canOpen,
  needsReason,
  setAmount,
  setReason,
  toPayload,
  totalFloat,
  unexplained,
  variance,
  type OpeningRow,
  type OpeningSuggestion,
  type ProfileMode,
} from "./openingBalances";

/** Indexing is checked here, so a missing row fails as a missing row, not as undefined. */
const row = (rows: OpeningRow[], index: number): OpeningRow => {
  const found = rows[index];
  if (!found) throw new Error(`expected a row at ${index}, got ${rows.length} rows`);
  return found;
};

const suggestion = (over: Partial<OpeningSuggestion> = {}): OpeningSuggestion => ({
  pos_profile: "Main Till",
  modes: [
    {
      mode_of_payment: "Cash",
      type: "Cash",
      carries_float: true,
      suggested_amount: 3000,
      previous_closing_amount: 3000,
      previous_closing_entry: "POS-CLO-0001",
      previous_closed_on: "2026-09-09 21:00:00",
    },
    {
      mode_of_payment: "Mpesa-111222",
      type: "Phone",
      carries_float: false,
      suggested_amount: 0,
      previous_closing_amount: 0,
      previous_closing_entry: null,
      previous_closed_on: null,
    },
  ],
  ...over,
});

const modes: ProfileMode[] = [
  { mode_of_payment: "Cash", type: "Cash", default: 1 },
  { mode_of_payment: "Mpesa-111222", type: "Phone" },
];
const cashMode: ProfileMode = { mode_of_payment: "Cash", type: "Cash", default: 1 };

describe("buildOpeningRows", () => {
  it("opens cash where the till last closed", () => {
    const cash = row(buildOpeningRows(modes, suggestion()), 0);

    expect(cash.amount).toBe(3000);
    expect(cash.previousClosing).toBe(3000);
    expect(cash.hasHistory).toBe(true);
  });

  it("opens a phone mode at zero and marks it floatless", () => {
    const mpesa = row(buildOpeningRows(modes, suggestion()), 1);

    expect(mpesa.amount).toBe(0);
    expect(mpesa.carriesFloat).toBe(false);
    expect(mpesa.hasHistory).toBe(false);
  });

  it("falls back to the mode's own type when no suggestion arrives", () => {
    const rows = buildOpeningRows(modes, null);

    expect(rows.map((r) => r.carriesFloat)).toEqual([true, false]);
    expect(totalFloat(rows)).toBe(0);
  });

  it("skips a row with no mode", () => {
    expect(buildOpeningRows([{ mode_of_payment: "" }], null)).toHaveLength(0);
  });
});

describe("what may be changed", () => {
  it("takes a new cash figure", () => {
    const rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 2500);

    expect(row(rows, 0).amount).toBe(2500);
    expect(variance(row(rows, 0))).toBe(-500);
  });

  it("refuses to put a float on a phone mode", () => {
    const rows = setAmount(buildOpeningRows(modes, suggestion()), 1, 500);

    expect(row(rows, 1).amount).toBe(0);
  });

  it("treats a blank input as zero rather than as not-a-number", () => {
    const rows = setAmount(buildOpeningRows(modes, suggestion()), 0, Number.NaN);

    expect(row(rows, 0).amount).toBe(0);
  });
});

describe("explaining a difference", () => {
  it("asks for a reason when cash opens short", () => {
    const rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 2500);

    expect(needsReason(row(rows, 0))).toBe(true);
    expect(unexplained(rows)).toHaveLength(1);
    expect(canOpen(rows)).toBe(false);
  });

  it("asks when it opens over, too", () => {
    const rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 3500);

    expect(variance(row(rows, 0))).toBe(500);
    expect(needsReason(row(rows, 0))).toBe(true);
  });

  it("accepts a reason", () => {
    let rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 2500);
    rows = setReason(rows, 0, "500 banked overnight, slip 4471");

    expect(needsReason(row(rows, 0))).toBe(false);
    expect(canOpen(rows)).toBe(true);
  });

  it("does not accept whitespace as one", () => {
    let rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 2500);
    rows = setReason(rows, 0, "   ");

    expect(needsReason(row(rows, 0))).toBe(true);
  });

  it("asks nothing of a till that has never closed", () => {
    const fresh = suggestion({
      modes: [
        {
          mode_of_payment: "Cash",
          type: "Cash",
          carries_float: true,
          suggested_amount: 0,
          previous_closing_amount: 0,
          previous_closing_entry: null,
          previous_closed_on: null,
        },
      ],
    });
    const rows = setAmount(buildOpeningRows([cashMode], fresh), 0, 1500);

    expect(variance(row(rows, 0))).toBe(0);
    expect(canOpen(rows)).toBe(true);
  });

  it("cannot open with no modes at all", () => {
    expect(canOpen([])).toBe(false);
  });
});

describe("what gets sent", () => {
  it("sends the reason with the amount it explains", () => {
    let rows = setAmount(buildOpeningRows(modes, suggestion()), 0, 2500);
    rows = setReason(rows, 0, "banked overnight");

    expect(toPayload(rows)).toEqual([
      { mode_of_payment: "Cash", opening_amount: 2500, variance_reason: "banked overnight" },
      { mode_of_payment: "Mpesa-111222", opening_amount: 0 },
    ]);
  });

  it("sends no reason when nothing changed", () => {
    const rows = setReason(buildOpeningRows(modes, suggestion()), 0, "typed then thought better of it");

    expect(toPayload(rows)[0]).toEqual({ mode_of_payment: "Cash", opening_amount: 3000 });
  });

  it("counts only float toward the total", () => {
    const rows = buildOpeningRows(modes, suggestion());

    expect(totalFloat(rows)).toBe(3000);
  });
});
