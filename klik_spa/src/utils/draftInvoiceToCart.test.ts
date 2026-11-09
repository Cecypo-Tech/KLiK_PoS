import { describe, expect, it, vi } from "vitest";
import { draftItemToCartItem, type InvoiceItem } from "./draftInvoiceToCart";
import { getEffectiveItemRate } from "./cartPricing";

vi.mock("react-toastify", () => ({ toast: { error: vi.fn() } }));

// What the cart charges once OrderSummary seeds itemDiscounts from the restored line.
const chargedRate = (row: Partial<InvoiceItem>) => {
  const line = draftItemToCartItem({ item_code: "PEN", item_name: "Pen", qty: 1, amount: 0, ...row } as InvoiceItem, 0);
  return getEffectiveItemRate(line, {
    itemDiscounts: {
      [line.id]: { discountPercentage: line.discount_percentage || 0, discountAmount: line.discount_amount || 0 },
    },
  });
};

describe("a recalled draft line charges the rate the draft saved", () => {
  it("a % discount (ERPNext stores it as both % and amount) is taken once", () => {
    expect(chargedRate({ price_list_rate: 100, discount_percentage: 10, discount_amount: 10, rate: 90 })).toBe(90);
  });

  it("an amount-only discount (rate edited) is unchanged", () => {
    expect(chargedRate({ price_list_rate: 600, discount_percentage: 0, discount_amount: 300, rate: 300 })).toBe(300);
  });

  it("no discount charges the list rate", () => {
    expect(chargedRate({ price_list_rate: 250, rate: 250 })).toBe(250);
  });

  it("a rate above the list rate (ERPNext margin) is kept, not dropped to the list rate", () => {
    expect(chargedRate({ price_list_rate: 600, rate: 700 })).toBe(700);
  });

  it("no list rate falls back to the saved rate", () => {
    expect(chargedRate({ price_list_rate: 0, rate: 80, discount_amount: 0 })).toBe(80);
  });
});
