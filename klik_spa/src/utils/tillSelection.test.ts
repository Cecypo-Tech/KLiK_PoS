import { describe, expect, it } from "vitest";
import { filterTills, onlyTill, onlyTills, toggleTill } from "./tillSelection";

const ALL = ["Charity - OJWANG - HQ", "Daisy - OJWANG - MILIMANI", "Vivian - OJWANG - HQ", "Cecypo"];

describe("till selection ([] means all tills)", () => {
  it("unticking one till from all keeps the rest", () => {
    expect(toggleTill([], ALL, "Cecypo")).toEqual(ALL.slice(0, 3));
  });

  it("ticking the last missing till goes back to all", () => {
    expect(toggleTill(ALL.slice(0, 3), ALL, "Cecypo")).toEqual([]);
  });

  it("unticking the only selected till is refused, not turned into all", () => {
    expect(toggleTill(["Cecypo"], ALL, "Cecypo")).toEqual(["Cecypo"]);
  });

  it("Only picks just that till", () => {
    expect(onlyTill(ALL, "Cecypo")).toEqual(["Cecypo"]);
    expect(onlyTill(["Cecypo"], "Cecypo")).toEqual([]);
  });

  it("Only matching picks the search results, in list order", () => {
    expect(onlyTills(ALL, filterTills(ALL, "hq"))).toEqual(["Charity - OJWANG - HQ", "Vivian - OJWANG - HQ"]);
    expect(onlyTills(ALL, ALL)).toEqual([]);
    expect(onlyTills(ALL, [])).toEqual([]);
  });

  it("search ignores case and extra spaces, and matches every word", () => {
    expect(filterTills(ALL, "  ojwang  hq ")).toEqual(["Charity - OJWANG - HQ", "Vivian - OJWANG - HQ"]);
    expect(filterTills(ALL, "")).toEqual(ALL);
    expect(filterTills(ALL, "nairobi")).toEqual([]);
  });
});
