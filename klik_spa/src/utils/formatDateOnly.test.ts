import { describe, expect, it } from "vitest";
import { formatDateOnly } from "./time";

describe("formatDateOnly", () => {
  it("shows the calendar date it was given", () => {
    expect(formatDateOnly("2026-09-14")).toBe("Sep 14, 2026");
  });

  it("ignores a trailing time", () => {
    expect(formatDateOnly("2026-01-01 00:30:00")).toBe("Jan 1, 2026");
  });

  it("does not shift the first of the month back a day", () => {
    // new Date("2026-03-01") is UTC midnight and reads as Feb 28 west of UTC.
    expect(formatDateOnly("2026-03-01")).toBe("Mar 1, 2026");
  });

  it("is empty for nothing and leaves non-dates alone", () => {
    expect(formatDateOnly("")).toBe("");
    expect(formatDateOnly(null)).toBe("");
    expect(formatDateOnly("Never")).toBe("Never");
  });
});
