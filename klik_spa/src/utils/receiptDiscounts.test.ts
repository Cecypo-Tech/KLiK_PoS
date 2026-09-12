import { describe, expect, it } from "vitest";
import { getLineDiscount, getItemDiscountTotal } from "./receiptDiscounts";

describe("getLineDiscount", () => {
  it("reports what came off a discounted line", () => {
    // The client's case: list 2,100, sold at 2,000, twenty of them.
    expect(getLineDiscount({ quantity: 20, listRate: 2100, sellRate: 2000 })).toBe(2000);
  });

  it("is zero when nothing came off", () => {
    expect(getLineDiscount({ quantity: 20, listRate: 2000, sellRate: 2000 })).toBe(0);
  });

  it("never reports a negative discount when the line sold above list", () => {
    expect(getLineDiscount({ quantity: 5, listRate: 100, sellRate: 120 })).toBe(0);
  });

  it("treats a missing list rate as no discount rather than a full-price giveaway", () => {
    expect(getLineDiscount({ quantity: 5, listRate: 0, sellRate: 120 })).toBe(0);
  });

  it("rounds to currency precision", () => {
    expect(getLineDiscount({ quantity: 3, listRate: 10.005, sellRate: 10 })).toBe(0.02);
  });
});

describe("getItemDiscountTotal", () => {
  it("adds up every discounted line and ignores the rest", () => {
    expect(
      getItemDiscountTotal([
        { quantity: 20, listRate: 2100, sellRate: 2000 },
        { quantity: 1, listRate: 500, sellRate: 500 },
        { quantity: 2, listRate: 300, sellRate: 250 },
      ]),
    ).toBe(2100);
  });

  it("is zero for an empty cart", () => {
    expect(getItemDiscountTotal([])).toBe(0);
  });
});
