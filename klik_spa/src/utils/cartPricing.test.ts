import { describe, expect, it } from "vitest";
import { getCartRowPctBasis, getEffectiveItemRate, getPreDiscountRate } from "./cartPricing";
import { discountAmountFromPct } from "./lineEdits";

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

describe("getPreDiscountRate (basis for a line discount %)", () => {
  const charged = (item: { id: string; price: number }, customRate: number | undefined, pct: number) => {
    const base = getPreDiscountRate(item, { itemDiscounts: { [item.id]: { customRate, discountAmount: 4 } } });
    const discountAmount = discountAmountFromPct(base, pct);
    return { discountAmount, rate: getEffectiveItemRate(item, { itemDiscounts: { [item.id]: { customRate, discountAmount } } }) };
  };

  it("is the custom rate on a custom-rate line: 10% of 80 is 8, charged 72", () => {
    expect(charged({ id: "A", price: 100 }, 80, 10)).toEqual({ discountAmount: 8, rate: 72 });
  });

  it("is the price on a plain line: 10% of 100 is 10, charged 90", () => {
    expect(charged({ id: "A", price: 100 }, undefined, 10)).toEqual({ discountAmount: 10, rate: 90 });
  });
});

describe("getCartRowPctBasis (the classic cart row's % basis)", () => {
  it("is the list price on a plain line, even with a restored discountPercentage: 10% of 100 is 10, as before", () => {
    const item = { id: "A", price: 100 };
    expect(discountAmountFromPct(getCartRowPctBasis(item, { discountPercentage: 10 }), 10)).toBe(10);
  });

  it("is the custom rate on a custom-rate line", () => {
    expect(getCartRowPctBasis({ id: "A", price: 100 }, { customRate: 80, discountAmount: 8 })).toBe(80);
  });
});
