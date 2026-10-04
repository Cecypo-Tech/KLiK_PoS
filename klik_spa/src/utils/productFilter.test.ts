import { describe, expect, it } from "vitest";
import type { MenuItem } from "../../types";
import { filterAvailableProducts } from "./productFilter";

const item = (id: string, extra: Partial<MenuItem> = {}): MenuItem =>
  ({ id, name: id, category: "G", price: 1, image: "", available: 0, sold: 0, is_stock_item: true, ...extra }) as MenuItem;

describe("filterAvailableProducts", () => {
  const products = [
    item("IN", { available: 2 }),
    item("OUT", { available: 0 }),
    item("SERVICE", { is_stock_item: false }),
    item("NEGATIVE", { allow_negative_stock: true }),
  ];

  it("hides only stock items with nothing on hand", () => {
    expect(filterAvailableProducts(products, true).map((p) => p.id)).toEqual(["IN", "SERVICE", "NEGATIVE"]);
  });

  it("hands the list back untouched when hiding is off", () => {
    expect(filterAvailableProducts(products, false)).toBe(products);
  });
});
