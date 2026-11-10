import { describe, expect, it } from "vitest";
import { clampRateToFloor, discountAmountFromPct, discountPctFromAmount, fractionInWholeUnit, rebaseOrderDiscount } from "./lineEdits";

describe("lineEdits", () => {
  it("clamps discount pct to 0..100", () => {
    expect(discountAmountFromPct(200, 150)).toBe(200);
    expect(discountAmountFromPct(200, -5)).toBe(0);
  });
  it("rounds the discount amount to 2 dp", () => {
    expect(discountAmountFromPct(99.99, 10)).toBe(10);
  });
  it("derives pct from amount, 0 when price is 0", () => {
    expect(discountPctFromAmount(200, 50)).toBe(25);
    expect(discountPctFromAmount(0, 5)).toBe(0);
  });
  it("clamps rate to the floor", () => {
    expect(clampRateToFloor(5, 8)).toBe(8);
    expect(clampRateToFloor(9, 8)).toBe(9);
    expect(clampRateToFloor(5, null)).toBe(5);
  });
});

describe("fractionInWholeUnit: a UOM marked Must be Whole Number takes no fraction, as ERPNext refuses on save", () => {
  const whole = ["Nos", "Box"];
  it("refuses a fraction in a whole-number unit", () => {
    expect(fractionInWholeUnit(2.5, "Nos", whole)).toBe(true);
  });
  it("allows a whole number, a fractional unit, or a till that sent no list", () => {
    expect(fractionInWholeUnit(3, "Nos", whole)).toBe(false);
    expect(fractionInWholeUnit(0.7 * 10, "Nos", whole)).toBe(false); // 7.000000000000001 from a typed sum
    expect(fractionInWholeUnit(2.5, "Kg", whole)).toBe(false);
    expect(fractionInWholeUnit(2.5, "Nos", undefined)).toBe(false);
    expect(fractionInWholeUnit(2.5, undefined, whole)).toBe(false);
  });
});

describe("rebaseOrderDiscount: the invoice discount follows the cart, as ERPNext's does", () => {
  it("a discount given in % keeps its % and its amount moves with the subtotal", () => {
    expect(rebaseOrderDiscount({ byPercent: true, percent: 5, amount: 152.5 }, 2000)).toEqual({ percent: 5, amount: 100 });
  });
  it("a discount given as an amount keeps its amount and its % moves", () => {
    expect(rebaseOrderDiscount({ byPercent: false, percent: 5, amount: 150 }, 2000)).toEqual({ percent: 7.5, amount: 150 });
    expect(rebaseOrderDiscount({ byPercent: false, percent: 5, amount: 150 }, 0)).toEqual({ percent: 0, amount: 150 });
  });
});
