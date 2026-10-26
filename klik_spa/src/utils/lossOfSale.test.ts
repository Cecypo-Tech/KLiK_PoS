import { describe, expect, it } from "vitest";
import { applyLosAdjustments, linesStockQty, losToast, noStockMessage, planLineQty, qtyToSend, splitForLoS } from "./lossOfSale";

const plan = (over: Partial<Parameters<typeof planLineQty>[0]> = {}) =>
  planLineQty({ limited: true, available: 10, requested: 16, otherLinesQty: 0, losEnabled: true, ...over });

describe("splitForLoS", () => {
  it("sells what is left and records the rest", () => {
    expect(splitForLoS(16, 10)).toEqual({ quantity: 10, los_qty: 6 });
  });
  it("keeps a zero line when nothing is left", () => {
    expect(splitForLoS(6, 0)).toEqual({ quantity: 0, los_qty: 6 });
  });
});

describe("planLineQty", () => {
  it("splits when LoS is on", () => {
    expect(plan()).toEqual({ quantity: 10, los_qty: 6 });
  });
  it("refuses when LoS is off", () => {
    expect(plan({ losEnabled: false })).toBeNull();
  });
  it("counts what the cart's other lines already take", () => {
    expect(plan({ otherLinesQty: 7, requested: 5 })).toEqual({ quantity: 3, los_qty: 2 });
  });
  it("leaves unlimited stock alone", () => {
    expect(plan({ limited: false, losEnabled: false })).toEqual({ quantity: 16, los_qty: 0 });
  });
  it("limits a line in another unit by the stock it converts to", () => {
    // 100 rolls in stock; the line sells by the kg, 15 kg to a roll.
    const kg = { available: 100, factor: 1 / 15 };
    expect(plan({ ...kg, requested: 200, losEnabled: false })).toEqual({ quantity: 200, los_qty: 0 });
    expect(plan({ ...kg, requested: 1600 })).toEqual({ quantity: 1500, los_qty: 100 });
    expect(plan({ ...kg, requested: 1600, losEnabled: false })).toBeNull();
    // Another line already holds 40 rolls.
    expect(plan({ ...kg, otherLinesQty: 40, requested: 1000 })).toEqual({ quantity: 900, los_qty: 100 });
  });
  it("treats a stepper minus as a smaller request", () => {
    // "10 + LoS 6", minus one: 15 requested
    expect(plan({ requested: 15 })).toEqual({ quantity: 10, los_qty: 5 });
  });
});

describe("applyLosAdjustments", () => {
  const cart = [
    { id: "A", item_code: "A", quantity: 16, los_qty: 0 },
    { id: "B", item_code: "B", quantity: 2, los_qty: 0 },
  ];
  it("applies corrections by position", () => {
    expect(applyLosAdjustments(cart, [{ index: 0, item_code: "A", quantity: 10, los_qty: 6 }])[0]).toMatchObject({
      quantity: 10,
      los_qty: 6,
    });
  });
  it("ignores a correction whose line has moved", () => {
    expect(applyLosAdjustments(cart, [{ index: 1, item_code: "A", quantity: 10, los_qty: 6 }])).toEqual(cart);
  });
});

it("losToast names the split", () => {
  expect(losToast("Tonic", "Nos", { quantity: 10, los_qty: 6 })).toBe(
    "Only 10 Nos of Tonic in stock: 6 recorded as Loss of Sale",
  );
});

describe("qtyToSend", () => {
  it("sends a qty retyped to the same value: on 10 + LoS 6, typing 10 means just the 10", () => {
    expect(qtyToSend(true, 10)).toBe(10);
  });
  it("sends nothing for a box left without an edit, so its LoS (or 0-qty LoS line) is kept", () => {
    expect(qtyToSend(false, 10)).toBeNull();
    expect(qtyToSend(false, 0)).toBeNull();
  });
});

describe("linesStockQty", () => {
  it("adds the item's other lines in stock units, whatever unit each is in", () => {
    const lines = [
      { id: "1", item_code: "WIRE", quantity: 2, conversion_factor: 1 },
      { id: "2", item_code: "WIRE", quantity: 30, conversion_factor: 1 / 15 },
      { id: "3", item_code: "NAIL", quantity: 9 },
    ];
    expect(linesStockQty(lines, "WIRE")).toBeCloseTo(4);
    expect(linesStockQty(lines, "WIRE", "1")).toBeCloseTo(2);
    expect(linesStockQty(lines, "NAIL")).toBe(9);
  });
});

it("noStockMessage states the stock in the line's unit", () => {
  expect(noStockMessage("Wire", "kg", 100, 1 / 15)).toBe("Only 1,500 kg of Wire available");
  expect(noStockMessage("Box", undefined, 5, 12)).toBe("Only 0.42 units of Box available");
});
