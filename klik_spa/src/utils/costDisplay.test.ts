import { describe, expect, it } from "vitest";
import { costMode, itemCostCell, pickCost } from "./costDisplay";

describe("costMode", () => {
  it("passes the two shown modes through", () => {
    expect(costMode({ custom_cost_display: "Valuation" })).toBe("Valuation");
    expect(costMode({ custom_cost_display: "Last Purchase Cost" })).toBe("Last Purchase Cost");
  });
  it("treats anything else, or no profile yet, as Hidden", () => {
    expect(costMode({ custom_cost_display: "Hidden" })).toBe("Hidden");
    expect(costMode({})).toBe("Hidden");
    expect(costMode(null)).toBe("Hidden");
  });
});

describe("pickCost", () => {
  it("shows valuation and offers last purchase on hover", () => {
    expect(pickCost("Valuation", 90, 100)).toEqual({ shown: 90, other: 100, otherLabel: "Last purchase" });
  });
  it("shows last purchase and offers valuation on hover", () => {
    expect(pickCost("Last Purchase Cost", 90, 100)).toEqual({ shown: 100, other: 90, otherLabel: "Valuation" });
  });
  it("treats a missing figure as 0", () => {
    expect(pickCost("Last Purchase Cost", 90, undefined)).toEqual({ shown: 0, other: 90, otherLabel: "Valuation" });
  });
});

describe("itemCostCell", () => {
  const fmt = (n: number) => `KES ${n.toFixed(2)}`;
  const item = { cost_price: 90, last_purchase_cost: 100, last_purchase_date: "2026-11-01" };
  it("valuation shown, last purchase and its date on hover", () => {
    expect(itemCostCell(item, "Valuation", fmt)).toEqual({ text: "KES 90.00", title: "Last purchase: KES 100.00 on 2026-11-01" });
  });
  it("last purchase shown, valuation on hover", () => {
    expect(itemCostCell(item, "Last Purchase Cost", fmt)).toEqual({ text: "KES 100.00", title: "Valuation: KES 90.00" });
  });
  it("says so when the item was never bought", () => {
    expect(itemCostCell({ cost_price: 90 }, "Valuation", fmt).title).toBe("Last purchase: no purchase invoice");
    expect(itemCostCell({ cost_price: 90 }, "Last Purchase Cost", fmt).text).toBe("—");
  });
  it("grosses both up by inclusive VAT", () => {
    const vat = { ...item, tax_info: { is_inclusive: true, total_tax_rate: 16 } };
    expect(itemCostCell(vat, "Valuation", fmt)).toEqual({
      text: "KES 104.40",
      title: "Last purchase: KES 116.00 on 2026-11-01 (costs incl. 16% VAT)",
    });
  });
});
