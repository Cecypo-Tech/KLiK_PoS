import { describe, expect, it } from "vitest";
import { clampRateToFloor, discountAmountFromPct, discountPctFromAmount, parseDecimalInput } from "./lineEdits";

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
  it("parses decimal input", () => {
    expect(parseDecimalInput("1,250.5")).toBe(1250.5);
    expect(parseDecimalInput("")).toBeUndefined();
    expect(parseDecimalInput("abc")).toBeUndefined();
  });
});
