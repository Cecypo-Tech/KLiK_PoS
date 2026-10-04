import { describe, expect, it } from "vitest";
import type { MenuItem } from "../../types";
import { applyStockUpdates, chunkCodes, stockRefreshCodes } from "./stockRefresh";

const item = (id: string, extra: Partial<MenuItem> = {}): MenuItem =>
  ({ id, name: id, category: "G", price: 1, image: "", available: 3, sold: 0, is_stock_item: true, ...extra }) as MenuItem;

describe("stockRefreshCodes", () => {
  it("asks only for plain stock items", () => {
    const products = [
      item("PLAIN"),
      item("BUNDLE", { is_product_bundle: true }),
      item("TEMPLATE", { is_variant_template: true, is_stock_item: false }),
      item("SERVICE", { is_stock_item: false }),
    ];
    expect(stockRefreshCodes(products)).toEqual(["PLAIN"]);
  });
});

describe("chunkCodes", () => {
  it("splits into requests of at most the given size", () => {
    expect(chunkCodes(["a", "b", "c", "d", "e"], 2)).toEqual([["a", "b"], ["c", "d"], ["e"]]);
    expect(chunkCodes([], 200)).toEqual([]);
  });
});

describe("applyStockUpdates", () => {
  it("keeps the very same list when nothing moved", () => {
    const products = [item("A", { available: 3 }), item("B", { available: 5 })];
    expect(applyStockUpdates(products, { A: 3, B: 5 })).toBe(products);
  });

  it("replaces only the items whose stock changed", () => {
    const a = item("A", { available: 3 });
    const b = item("B", { available: 5 });
    const next = applyStockUpdates([a, b], { A: 0, B: 5 });
    expect(next[0]).not.toBe(a);
    expect(next[0]?.available).toBe(0);
    expect(next[1]).toBe(b);
  });

  it("never overwrites a bundle's or a template's own availability", () => {
    const bundle = item("BUNDLE", { is_product_bundle: true, available: 4 });
    const template = item("TEMPLATE", { is_variant_template: true, is_stock_item: false, available: 6 });
    const products = [bundle, template];
    expect(applyStockUpdates(products, { BUNDLE: 0, TEMPLATE: 0 })).toBe(products);
  });

  it("converts the stock-UOM quantity to the selling UOM, rounding down like the listing", () => {
    const box = item("BOX", { available: 1, conversion_factor: 10 });
    const next = applyStockUpdates([box], { BOX: 25 });
    expect(next[0]?.available).toBe(2);
    expect(applyStockUpdates(next, { BOX: 25 })).toBe(next);
  });

  it("keeps fractional stock of an item sold in its stock UOM", () => {
    const kg = item("KG", { available: 1 });
    expect(applyStockUpdates([kg], { KG: 0.5 })[0]?.available).toBe(0.5);
  });
});
