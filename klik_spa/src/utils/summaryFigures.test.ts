import { describe, expect, it } from "vitest";
import { summaryFigures } from "./summaryFigures";

const adds = (f: { subtotal: number; discount: number; tax: number }, shipping = 0) =>
  Math.round((f.subtotal - f.discount + f.tax + shipping) * 100) / 100;

describe("summaryFigures", () => {
  it("with no discount the subtotal is the server's net total", () => {
    const f = summaryFigures({ netTotal: 215.52, taxTotal: 34.48, grandTotal: 250, discount: 0, shipping: 0 });
    expect(f).toEqual({ subtotal: 215.52, discount: 0, tax: 34.48 });
    expect(adds(f)).toBe(250);
  });

  it("shows an order discount before tax, so Subtotal - Discount + Tax = Grand Total", () => {
    // 250 inclusive, 50 off the grand total: ERPNext's net_total 172.41 already has it out.
    const f = summaryFigures({ netTotal: 172.41, taxTotal: 27.59, grandTotal: 200, discount: 50, shipping: 0 });
    expect(f.subtotal).toBe(215.51);
    expect(f.discount).toBe(43.1);
    expect(f.tax).toBe(27.59);
    expect(adds(f)).toBe(200);
  });

  it("keeps a shipping charge out of the tax and out of the discount split", () => {
    const f = summaryFigures({ netTotal: 100, taxTotal: 116, grandTotal: 216, discount: 0, shipping: 100 });
    expect(f).toEqual({ subtotal: 100, discount: 0, tax: 16 });
    expect(adds(f, 100)).toBe(216);
  });

  it("adds up to the cent even where ERPNext's own figures are a cent apart", () => {
    // Real dev preview: 850 exclusive sale, 50 off. net 689.66 + tax 110.35 = 800.01, yet
    // ERPNext's grand total is 800.00; the discount takes the cent.
    const f = summaryFigures({ netTotal: 689.66, taxTotal: 110.35, grandTotal: 800, discount: 50, shipping: 0 });
    expect(f.subtotal).toBe(732.76);
    expect(adds(f)).toBe(800);
  });
});
