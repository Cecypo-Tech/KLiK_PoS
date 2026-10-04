import { describe, expect, it } from "vitest";
import { applyLosAdjustments, losToast, planLineQty, splitForLoS } from "./lossOfSale";

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
