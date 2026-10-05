import { describe, expect, it } from "vitest";
import { inDateRange, localDay, storedDate } from "./dateRange";

describe("inDateRange", () => {
  it("is unbounded when both ends are empty", () => {
    expect(inDateRange("2020-01-01", "", "")).toBe(true);
  });

  it("includes both end days", () => {
    expect(inDateRange("2026-10-03", "2026-10-03", "2026-10-10")).toBe(true);
    expect(inDateRange("2026-10-10", "2026-10-03", "2026-10-10")).toBe(true);
  });

  it("leaves out days outside the range", () => {
    expect(inDateRange("2026-10-02", "2026-10-03", "")).toBe(false);
    expect(inDateRange("2026-10-11", "", "2026-10-10")).toBe(false);
  });

  it("compares the calendar day as written, not shifted to UTC", () => {
    // new Date("2026-10-04") is UTC midnight - the 3rd in any zone west of Greenwich.
    expect(inDateRange("2026-10-04", "2026-10-04", "2026-10-04")).toBe(true);
    expect(inDateRange("2026-10-04 23:30:00", "2026-10-04", "2026-10-04")).toBe(true);
  });

  it("leaves out an undated row once a bound is set", () => {
    expect(inDateRange("", "2026-10-04", "")).toBe(false);
  });
});

describe("storedDate", () => {
  it("keeps a yyyy-mm-dd value and drops anything else", () => {
    expect(storedDate("2026-10-04")).toBe("2026-10-04");
    expect(storedDate("today")).toBe("");
    expect(storedDate(undefined)).toBe("");
    expect(storedDate(42)).toBe("");
  });
});

describe("localDay", () => {
  it("gives today and yesterday as local calendar days", () => {
    const now = new Date(2026, 9, 5, 23, 30); // late evening, local time
    expect(localDay(0, now)).toBe("2026-10-05");
    expect(localDay(-1, now)).toBe("2026-10-04");
  });

  it("crosses a month boundary", () => {
    expect(localDay(-1, new Date(2026, 9, 1, 8))).toBe("2026-09-30");
  });
});
