import { describe, expect, it } from "vitest";

import type { CartItem } from "../../types";
import { addEntries, moveLine } from "./bulkAdd";

const item = (id: string, over: Partial<CartItem> = {}) =>
  ({ id, item_code: id, name: id, price: 10, uom: "Nos", available: 100, item_tax_template: "T", ...over }) as unknown as CartItem;
const helpers = {
  limited: (i: { available?: number }) => typeof i.available === "number",
  losEnabled: () => false,
  insertAtTop: false,
};

describe("addEntries", () => {
  it("adds new lines in order", () => {
    const result = addEntries([], [{ item: item("A"), qty: 2 }, { item: item("B"), qty: 1 }], helpers);
    expect(result.cartItems.map((c) => [c.id, c.quantity])).toEqual([["A", 2], ["B", 1]]);
    expect(result.lineIds).toEqual(["A", "B"]);
    expect(result.cartItems[0]?.item_tax_template).toBe("T");
  });

  it("merges two entries for the same item into one line", () => {
    const result = addEntries([], [{ item: item("A"), qty: 2 }, { item: item("A"), qty: 3 }], helpers);
    expect(result.cartItems.map((c) => [c.id, c.quantity])).toEqual([["A", 5]]);
    expect(result.lineIds).toEqual(["A", "A"]);
  });

  it("adds onto a line already in the cart", () => {
    const result = addEntries([{ ...item("A"), quantity: 4 } as CartItem], [{ item: item("A"), qty: 1 }], helpers);
    expect(result.cartItems[0]?.quantity).toBe(5);
  });

  it("refuses what stock cannot cover and says so, adding the rest", () => {
    const result = addEntries([], [{ item: item("A", { available: 1 }), qty: 3 }, { item: item("B"), qty: 1 }], helpers);
    expect(result.lineIds).toEqual([null, "B"]);
    expect(result.refusals).toEqual(["Only 1 Nos of A available"]);
  });

  it("checks a line in another unit against the stock it converts to", () => {
    // 100 rolls in stock; the cart line was switched to kg, 15 kg to a roll.
    const kgLine = { ...item("W", { uom: "kg", conversion_factor: 1 / 15 }), quantity: 1000 } as CartItem;
    const roll = item("W", { uom: "Roll", conversion_factor: 1, available: 100 });
    expect(addEntries([kgLine], [{ item: roll, qty: 400 }], helpers).cartItems[0]?.quantity).toBe(1400);
    const refused = addEntries([kgLine], [{ item: roll, qty: 600 }], helpers);
    expect(refused.cartItems[0]?.quantity).toBe(1000);
    expect(refused.refusals).toEqual(["Only 1,500 kg of W available"]);
  });

  it("puts new lines on top when the till says so", () => {
    const result = addEntries([{ ...item("Z"), quantity: 1 } as CartItem], [{ item: item("A"), qty: 1 }], {
      ...helpers,
      insertAtTop: true,
    });
    expect(result.cartItems.map((c) => c.id)).toEqual(["A", "Z"]);
  });

  it("records the shortfall as Loss of Sale when the till does that", () => {
    const result = addEntries([], [{ item: item("A", { available: 1 }), qty: 3 }], { ...helpers, losEnabled: () => true });
    expect(result.cartItems[0]).toMatchObject({ quantity: 1, los_qty: 2 });
    expect(result.warnings).toHaveLength(1);
  });
});

describe("moveLine", () => {
  it("moves a line to the top or the bottom", () => {
    const items = ["A", "B", "C"].map((id) => item(id));
    expect(moveLine(items, "B", true).map((c) => c.id)).toEqual(["B", "A", "C"]);
    expect(moveLine(items, "B", false).map((c) => c.id)).toEqual(["A", "C", "B"]);
  });
});
