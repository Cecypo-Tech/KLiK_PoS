import { describe, expect, it } from "vitest";
import { exclusiveSubtotal, formatSummaryTaxLabel, formatTaxLabel, getTaxRateForDisplay } from "./taxLabel";

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

describe("formatSummaryTaxLabel", () => {
  it("names the rate without Incl./Excl. - the summary adds the tax to a pre-tax subtotal either way", () => {
    expect(formatSummaryTaxLabel(16)).toBe("Tax (16%)");
    expect(formatSummaryTaxLabel(12.5)).toBe("Tax (12.5%)");
    expect(formatSummaryTaxLabel(null)).toBe("Tax");
  });
});

describe("exclusiveSubtotal", () => {
  it("takes the tax out of a tax-inclusive subtotal", () => {
    expect(exclusiveSubtotal(250, true, 16)).toBe(215.52);
  });

  it("leaves a tax-exclusive subtotal alone", () => {
    expect(exclusiveSubtotal(250, false, 16)).toBe(250);
  });

  it("leaves it alone when the rate is unknown", () => {
    expect(exclusiveSubtotal(250, true, null)).toBe(250);
  });
});
