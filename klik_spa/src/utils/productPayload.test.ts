import { describe, expect, it } from "vitest";
import type { ItemTaxInfo, MenuItem } from "../../types";
import { expandTaxProfiles } from "./productPayload";

const vat: ItemTaxInfo = { has_vat: true, is_inclusive: true, total_tax_rate: 16 };
const item = (id: string, extra: Record<string, unknown> = {}) =>
  ({ id, name: id, category: "G", price: 1, image: "", available: 1, sold: 0, ...extra }) as unknown as MenuItem;

describe("expandTaxProfiles", () => {
  it("gives every item its tax details back from the shared profile", () => {
    const expanded = expandTaxProfiles([item("A", { tax_key: "t0" }), item("B", { tax_key: "t0" })], { t0: vat });
    expect(expanded.every((p) => p.tax_info === vat)).toBe(true);
    expect(expanded.some((p) => "tax_key" in p)).toBe(false);
  });

  it("leaves a page without profiles as it came", () => {
    const items = [item("A", { tax_info: vat })];
    expect(expandTaxProfiles(items, undefined)).toBe(items);
  });

  it("leaves an item without a key alone", () => {
    const plain = item("A");
    expect(expandTaxProfiles([plain], { t0: vat })[0]).toBe(plain);
  });
});
