import { describe, it, expect } from "vitest";
import { getInclusiveTaxRate, getCostMargin } from "./costMargin";

describe("getInclusiveTaxRate", () => {
  it("uses the inclusive portion only, not the total, for mixed tax lines", () => {
    expect(getInclusiveTaxRate({ is_inclusive: true, total_tax_rate: 18, inclusive_tax_rate: 16 })).toBe(16);
  });

  it("falls back to the total when only the is_inclusive flag is known", () => {
    expect(getInclusiveTaxRate({ is_inclusive: true, total_tax_rate: 16 })).toBe(16);
  });

  it("is 0 for exclusive tax, no tax, and missing tax info", () => {
    expect(getInclusiveTaxRate({ is_inclusive: false, total_tax_rate: 16, inclusive_tax_rate: 0 })).toBe(0);
    expect(getInclusiveTaxRate({ is_inclusive: false, total_tax_rate: 0 })).toBe(0);
    expect(getInclusiveTaxRate(undefined)).toBe(0);
  });
});

describe("getCostMargin", () => {
  it("grosses the cost up by inclusive VAT before comparing with the inclusive sell price", () => {
    // Valuation 400 excl. VAT, 16% VAT, selling at 450 incl. VAT: cost 464, a 14 loss.
    const result = getCostMargin({ sellPrice: 450, costPerStockUom: 400, inclusiveTaxRate: 16 });
    expect(result.costInclTax).toBeCloseTo(464);
    expect(result.margin).toBeCloseTo(-14);
  });

  it("compares like with like when nothing is tax-inclusive", () => {
    const result = getCostMargin({ sellPrice: 500, costPerStockUom: 100, inclusiveTaxRate: 0 });
    expect(result.costInclTax).toBe(100);
    expect(result.margin).toBe(400);
  });

  it("converts a per-stock-UOM cost to the selling UOM", () => {
    // 100 per Nos, sold by the Box of 12 at 1500.
    const result = getCostMargin({ sellPrice: 1500, costPerStockUom: 100, inclusiveTaxRate: 0, conversionFactor: 12 });
    expect(result.costInclTax).toBe(1200);
    expect(result.margin).toBe(300);
  });

  it("treats a missing or zero conversion factor as 1", () => {
    expect(getCostMargin({ sellPrice: 10, costPerStockUom: 4, inclusiveTaxRate: 0, conversionFactor: 0 }).margin).toBe(6);
  });
});
