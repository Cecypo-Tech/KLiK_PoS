import { describe, expect, it } from "vitest";

import { failureReason, parseQuickEntry, planQuickEntry, type MatchResult } from "./quickEntry";

const item = (id: string) => ({ id, item_code: id, name: id, price: 100, uom: "Nos" });

describe("parseQuickEntry", () => {
  it("reads item, qty and an optional rate per line", () => {
    expect(parseQuickEntry("mimosa,1\ntwist300, 5, 220")).toEqual([
      { line: 1, text: "mimosa,1", query: "mimosa", qty: 1, rate: null, error: null },
      { line: 2, text: "twist300, 5, 220", query: "twist300", qty: 5, rate: 220, error: null },
    ]);
  });

  it("skips blank lines and the dashes people paste around a list", () => {
    const lines = parseQuickEntry("---------\n\nmimosa,1\n   \n--------");
    expect(lines.map((l) => l.query)).toEqual(["mimosa"]);
    expect(lines[0]?.line).toBe(3);
  });

  it("treats an empty rate as the till's price", () => {
    expect(parseQuickEntry("mimosa, 2, ")[0]).toMatchObject({ qty: 2, rate: null, error: null });
  });

  it("accepts decimal quantities and rates", () => {
    expect(parseQuickEntry("rope, 2.5, 99.50")[0]).toMatchObject({ qty: 2.5, rate: 99.5 });
    expect(parseQuickEntry("rope, .5")[0]).toMatchObject({ qty: 0.5, error: null });
  });

  it("reads rows pasted from a spreadsheet", () => {
    expect(parseQuickEntry("twist300\t5\t220")[0]).toMatchObject({ query: "twist300", qty: 5, rate: 220 });
  });

  it("does not take a zero rate as free", () => {
    expect(parseQuickEntry("rope, 1, 0")[0]?.error).toMatch(/more than 0/);
  });

  it("explains a line it cannot read", () => {
    const errors = parseQuickEntry("mimosa\n,3\nmimosa,0\nmimosa,-1\nmimosa,two\nmimosa,1,cheap\nmimosa,1,-5\nmimosa,1,2,3").map(
      (l) => l.error
    );
    expect(errors).toEqual([
      "Quantity is missing",
      "Item is missing",
      "Quantity must be more than 0",
      "Quantity must be more than 0",
      "Quantity must be a number",
      "Rate must be a number",
      "Rate must be more than 0 (leave it out for the till's price)",
      "Too many values: enter item, qty, rate",
    ]);
  });
});

describe("failureReason", () => {
  it("says what went wrong in the cashier's words", () => {
    const base = { query: "twist30", item: null };
    expect(failureReason({ ...base, status: "none", candidates: [] })).toBe('No item matches "twist30"');
    expect(failureReason({ ...base, status: "many", candidates: ["T300", "T3000"] })).toBe(
      'Several items match "twist30": T300, T3000'
    );
    expect(failureReason({ ...base, status: "template", candidates: ["SHIRT"] })).toBe(
      "SHIRT has variants: enter the variant's code"
    );
    expect(failureReason({ ...base, status: "unavailable", candidates: ["T300"] })).toBe(
      "T300 is not available on this till"
    );
  });
});

describe("planQuickEntry", () => {
  const parsed = parseQuickEntry("mimosa,1\ntwist30,2\nrope,1,50\nbad");
  const results: MatchResult[] = [
    { query: "mimosa", status: "ok", item: item("MIMOSA"), candidates: ["MIMOSA"] },
    { query: "twist30", status: "many", item: null, candidates: ["T300", "T3000"] },
    { query: "rope", status: "ok", item: item("ROPE"), candidates: ["ROPE"] },
  ];

  it("adds what matched and keeps the rest, with reasons", () => {
    const plan = planQuickEntry(parsed, results, { allowRateChange: true });
    expect(plan.toAdd).toEqual([
      { line: 1, item: item("MIMOSA"), qty: 1, rate: null },
      { line: 3, item: item("ROPE"), qty: 1, rate: 50 },
    ]);
    expect(plan.failed).toEqual([
      { line: 2, text: "twist30,2", reason: 'Several items match "twist30": T300, T3000' },
      { line: 4, text: "bad", reason: "Quantity is missing" },
    ]);
  });

  it("refuses a rate on a till that does not allow changing the price", () => {
    const plan = planQuickEntry(parsed, results, { allowRateChange: false });
    expect(plan.toAdd.map((a) => a.line)).toEqual([1]);
    expect(plan.failed[1]).toEqual({ line: 3, text: "rope,1,50", reason: "This till does not allow changing the price" });
  });
});
