import { describe, expect, it } from "vitest";
import { creditSalesAllowed } from "./creditSales";

describe("creditSalesAllowed", () => {
  it("follows the till's one Allow Credit Sales checkbox", () => {
    expect(creditSalesAllowed({ custom_allow_credit_sales_as_pos: 1 })).toBe(true);
    expect(creditSalesAllowed({ custom_allow_credit_sales_as_pos: 0 })).toBe(false);
    expect(creditSalesAllowed(null)).toBe(false);
  });

  it("is not opened by Allow Partial Payment, nor by the dropped second checkbox", () => {
    expect(creditSalesAllowed({ allow_partial_payment: 1, custom_allow_credit_sales: 1 })).toBe(false);
  });
});
