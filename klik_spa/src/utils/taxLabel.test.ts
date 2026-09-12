import { describe, expect, it } from "vitest";
import { getTaxRateForDisplay, formatTaxLabel } from "./taxLabel";

describe("getTaxRateForDisplay", () => {
  it("reads the rate off a single backend tax line", () => {
    expect(getTaxRateForDisplay([{ rate: 16, charge_type: "On Net Total" }])).toBe(16);
  });

  it("falls back to the selected template's rate when there is no breakdown", () => {
    expect(getTaxRateForDisplay([], 16)).toBe(16);
  });

  it("returns null when nothing knows the rate", () => {
    // This is the bug: the label rendered "Tax (% Excl.)" instead of admitting it.
    expect(getTaxRateForDisplay([], undefined)).toBeNull();
    expect(getTaxRateForDisplay([])).toBeNull();
  });

  it("prefers the backend breakdown over the selected template", () => {
    expect(getTaxRateForDisplay([{ rate: 16, charge_type: "On Net Total" }], 5)).toBe(16);
  });

  it("adds up several net-total lines, which is what a customer is charged", () => {
    expect(
      getTaxRateForDisplay([
        { rate: 16, charge_type: "On Net Total" },
        { rate: 2, charge_type: "On Net Total" },
      ]),
    ).toBe(18);
  });

  it("refuses to invent a combined rate when a line compounds on another", () => {
    // "On Previous Row Total" is not additive - 16 + 2 would be a lie.
    expect(
      getTaxRateForDisplay([
        { rate: 16, charge_type: "On Net Total" },
        { rate: 2, charge_type: "On Previous Row Total" },
      ]),
    ).toBeNull();
  });

  it("ignores zero-rate lines rather than counting them as a rate", () => {
    expect(getTaxRateForDisplay([{ rate: 0, charge_type: "On Net Total" }], 16)).toBe(16);
  });

  it("treats a line with no charge_type as applying to the net total", () => {
    expect(getTaxRateForDisplay([{ rate: 16 }])).toBe(16);
  });
});

describe("formatTaxLabel", () => {
  it("names the rate when it is known", () => {
    expect(formatTaxLabel(16, true)).toBe("Tax (16% Incl.)");
    expect(formatTaxLabel(16, false)).toBe("Tax (16% Excl.)");
  });

  it("keeps a fractional rate readable", () => {
    expect(formatTaxLabel(7.5, false)).toBe("Tax (7.5% Excl.)");
  });

  it("drops the percentage rather than printing an empty one", () => {
    expect(formatTaxLabel(null, true)).toBe("Tax (Incl.)");
    expect(formatTaxLabel(null, false)).toBe("Tax (Excl.)");
  });
});
