import { describe, expect, it } from "vitest";
import { getEffectiveItemRate } from "./cartPricing";

describe("getEffectiveItemRate", () => {
  it("takes a line discount off a custom rate", () => {
    const item = { id: "A", price: 100 };
    expect(getEffectiveItemRate(item, { itemDiscounts: { A: { customRate: 80, discountAmount: 4 } } })).toBe(76);
  });

  it("takes it off after converting a tax-inclusive custom rate", () => {
    const item = { id: "A", price: 100, total_tax_rate: 16, tax_templates: [{ is_inclusive: false }] };
    expect(getEffectiveItemRate(item, { itemDiscounts: { A: { customRate: 116, discountAmount: 5 } } })).toBe(95);
  });
});
