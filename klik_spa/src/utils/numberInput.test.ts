import { describe, expect, it } from "vitest";
import { evaluateNumber, formatNumber, isExpression } from "./numberInput";
import { parseDecimalInput } from "./lineEdits";

describe("evaluateNumber: a number field takes a sum, like ERPNext's", () => {
  it.each([
    ["20", 20],
    ["24.5", 24.5],
    ["4*5", 20],
    ["(450-50)/2", 200],
    ["1,000*2", 2000],
    [" 2 + 3 * 4 ", 14],
    ["-5+10", 5],
    ["10/4", 2.5],
    ["0.1+0.2", 0.3],
  ])("%s = %s", (text, expected) => {
    expect(evaluateNumber(text)).toBeCloseTo(expected as number, 10);
  });

  it.each(["", "  ", "abc", "2*", "(2+3", "2+3)", "4/0", "alert(1)", "2**3", "1e3"])("refuses %j", (text) => {
    expect(evaluateNumber(text)).toBeUndefined();
  });

  it("rounds away float noise", () => {
    expect(evaluateNumber("0.1*3")).toBe(0.3);
  });
});

describe("isExpression: only a sum earns the live result hint", () => {
  it("is false for a plain or negative number", () => {
    expect(isExpression("20")).toBe(false);
    expect(isExpression("-20")).toBe(false);
    expect(isExpression("1,000.50")).toBe(false);
  });
  it("is true once an operator follows a number", () => {
    expect(isExpression("4*5")).toBe(true);
    expect(isExpression("(2)")).toBe(true);
  });
});

describe("formatNumber", () => {
  it("money: two decimals with thousands separators", () => {
    expect(formatNumber(14500, "money")).toBe("14,500.00");
    expect(formatNumber(24.5, "money")).toBe("24.50");
  });
  it("percent: two decimals", () => {
    expect(formatNumber(2, "percent")).toBe("2.00");
  });
  it("qty: its own decimals, up to three", () => {
    expect(formatNumber(20, "qty")).toBe("20");
    expect(formatNumber(2.5, "qty")).toBe("2.5");
    expect(formatNumber(0.375, "qty")).toBe("0.375");
    expect(formatNumber(1250, "qty")).toBe("1,250");
  });
});

describe("parseDecimalInput evaluates sums for every caller", () => {
  it("works out a sum and still reads plain numbers", () => {
    expect(parseDecimalInput("4*5")).toBe(20);
    expect(parseDecimalInput("1,250.5")).toBe(1250.5);
    expect(parseDecimalInput("abc")).toBeUndefined();
  });
});
