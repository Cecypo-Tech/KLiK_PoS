import { describe, expect, it } from "vitest";
import { formatAmount, formatCurrencyWithSymbol } from "./currency";

describe("formatAmount", () => {
  it("formats without a symbol", () => {
    expect(formatAmount(150400)).toBe("150,400.00");
    expect(formatAmount(undefined as never)).toBe("0.00");
  });
  it("leaves the symbol form unchanged", () => {
    expect(formatCurrencyWithSymbol(2700, "KES")).toBe("KES 2,700.00");
  });
});
