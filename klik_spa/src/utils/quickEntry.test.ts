import { describe, expect, it } from "vitest";

import { problemsFirst, reviewOutcome, rowProblem, splitLines, toRows, withMatch, type ResolvedLine, type ReviewRow } from "./quickEntry";

const item = (id: string) => ({ id, item_code: id, name: id, price: 100, uom: "Nos" });
const ok = (text: string, over: Partial<ResolvedLine> = {}): ResolvedLine => ({
  text,
  status: "ok",
  qty: 1,
  qty_ambiguous: false,
  rate: null,
  item: item(text),
  candidates: [],
  reason: null,
  ...over,
});
const row = (line: number, answer: ResolvedLine): ReviewRow => ({ ...answer, line, skip: false });
const ctx = { allowRateChange: true, isOutOfStock: () => false };

describe("splitLines", () => {
  it("numbers lines as the box shows them, skipping blanks and separators", () => {
    expect(splitLines("-----\n\nAP004 2\n  \n5pcs AP377\n=====")).toEqual([
      { line: 3, text: "AP004 2" },
      { line: 5, text: "5pcs AP377" },
    ]);
  });
});

describe("toRows", () => {
  it("pairs each line with its answer", () => {
    expect(toRows([{ line: 3, text: "a" }], [ok("a")])).toEqual([{ ...ok("a"), line: 3, skip: false }]);
  });
});

describe("rowProblem", () => {
  it("passes a clean row", () => {
    expect(rowProblem(row(1, ok("A")), ctx)).toBeNull();
  });
  it("gives the server's reason for an unmatched row", () => {
    expect(rowProblem(row(1, ok("X", { status: "none", item: null, reason: 'No item matches "X"' })), ctx)).toBe(
      'No item matches "X"'
    );
  });
  it("asks to check an ambiguous quantity", () => {
    expect(rowProblem(row(1, ok("A", { qty_ambiguous: true })), ctx)).toBe(
      "Check the quantity: the line has more than one number"
    );
  });
  it("refuses a rate the till does not allow", () => {
    expect(rowProblem(row(1, ok("A", { rate: 50 })), { ...ctx, allowRateChange: false })).toBe(
      "This till does not allow changing the price"
    );
  });
  it("refuses an out-of-stock item", () => {
    expect(rowProblem(row(1, ok("A")), { ...ctx, isOutOfStock: () => true })).toBe("A is out of stock");
  });
  it("refuses a quantity the cashier cleared", () => {
    expect(rowProblem(row(1, ok("A", { qty: 0 })), ctx)).toBe("Quantity must be more than 0");
  });
});

describe("reviewOutcome", () => {
  it("adds ready rows, leaves skipped ones out, and blocks on the rest", () => {
    const rows = [
      row(1, ok("A", { qty: 2, rate: 50 })),
      { ...row(2, ok("X", { status: "none", item: null, reason: "no" })), skip: true },
      row(3, ok("Y", { status: "many", item: null, reason: "pick" })),
    ];
    const outcome = reviewOutcome(rows, ctx);
    expect(outcome.toAdd).toEqual([{ line: 1, item: item("A"), qty: 2, rate: 50 }]);
    expect(outcome.skipped.map((r) => r.line)).toEqual([2]);
    expect(outcome.blocked.map((r) => r.line)).toEqual([3]);
  });
});

describe("withMatch", () => {
  it("takes the new item but keeps the row's quantity, rate and line", () => {
    const before = { ...row(4, ok("twist", { status: "many", item: null, qty: 5, rate: 9, reason: "pick" })), skip: true };
    const after = withMatch(before, ok("T300", { qty: 1 }));
    expect(after).toMatchObject({
      line: 4,
      text: "twist",
      qty: 5,
      rate: 9,
      status: "ok",
      item: item("T300"),
      reason: null,
      skip: false,
    });
  });
});

describe("problemsFirst", () => {
  it("lists the lines that need a look first, each group in line order", () => {
    const rows = [
      row(1, ok("A")),
      row(2, ok("X", { status: "none", item: null, reason: "no" })),
      row(3, ok("B")),
      row(4, ok("C", { qty_ambiguous: true })),
    ];
    expect(problemsFirst(rows, ctx).map((r) => r.line)).toEqual([2, 4, 1, 3]);
  });
});
