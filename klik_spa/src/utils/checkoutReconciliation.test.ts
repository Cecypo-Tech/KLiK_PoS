import { describe, expect, it } from "vitest";
import { reconcileCheckout } from "./checkoutReconciliation";

const cart = [{ item_code: "WIRE", qty: 20, rate: 2000 }];

describe("reconcileCheckout", () => {
  it("passes when the server priced the line the way the till did", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "WIRE", qty: 20, rate: 2000, amount: 40000 },
    ]);
    expect(result.ok).toBe(true);
    expect(result.message).toBeNull();
    expect(result.extraCharges).toEqual([]);
  });

  it("fails, naming both prices, when the server repriced the line", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "WIRE", qty: 20, rate: 2205, amount: 44100 },
    ]);
    expect(result.ok).toBe(false);
    expect(result.message).toContain("WIRE");
    expect(result.message).toContain("2000");
    expect(result.message).toContain("2205");
  });

  it("fails when the server dropped a line the cart has", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "DELIVERY", qty: 1, rate: 4100, amount: 4100 },
    ]);
    expect(result.ok).toBe(false);
    expect(result.message).toContain("WIRE");
  });

  it("fails when the server changed the quantity", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "WIRE", qty: 21, rate: 2000, amount: 42000 },
    ]);
    expect(result.ok).toBe(false);
    expect(result.message).toContain("WIRE");
  });

  it("reports a server-added charge as an extra charge, not a mismatch", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "WIRE", qty: 20, rate: 2000, amount: 40000 },
      { item_code: "DELIVERY", qty: 1, rate: 4100, amount: 4100 },
    ]);
    expect(result.ok).toBe(true);
    expect(result.extraCharges).toEqual([{ item_code: "DELIVERY", amount: 4100 }]);
  });

  it("tolerates sub-cent rounding between the two sides", () => {
    const result = reconcileCheckout(cart, [
      { item_code: "WIRE", qty: 20, rate: 2000.004, amount: 40000.08 },
    ]);
    expect(result.ok).toBe(true);
  });

  it("passes on an empty cart and empty preview", () => {
    const result = reconcileCheckout([], []);
    expect(result.ok).toBe(true);
    expect(result.extraCharges).toEqual([]);
  });
});
