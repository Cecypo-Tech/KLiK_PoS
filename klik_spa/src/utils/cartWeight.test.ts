import { describe, expect, it } from "vitest";
import { formatCartWeight, getCartNetWeight } from "./cartWeight";

describe("getCartNetWeight", () => {
  it("adds quantity x weight per unit across lines", () => {
    const weight = getCartNetWeight([
      { quantity: 3, weight_per_unit: 5, weight_uom: "Kg" },
      { quantity: 2, weight_per_unit: 1.25, weight_uom: "Kg" },
    ]);
    expect(weight).toEqual({ total: 17.5, uom: "Kg", mixedUoms: false });
  });

  it("converts a line sold in a bigger UOM to stock units first", () => {
    // 2 boxes of 12, each unit 0.5 kg.
    const weight = getCartNetWeight([{ quantity: 2, conversion_factor: 12, weight_per_unit: 0.5, weight_uom: "Kg" }]);
    expect(weight.total).toBe(12);
  });

  it("ignores lines with no weight", () => {
    const weight = getCartNetWeight([
      { quantity: 4 },
      { quantity: 1, weight_per_unit: 0 },
      { quantity: 1, weight_per_unit: 2, weight_uom: "Kg" },
    ]);
    expect(weight).toEqual({ total: 2, uom: "Kg", mixedUoms: false });
  });

  it("is zero for an empty or weightless cart", () => {
    expect(getCartNetWeight([]).total).toBe(0);
    expect(getCartNetWeight([{ quantity: 5 }]).total).toBe(0);
  });

  it("drops the unit when lines disagree, rather than print a wrong one", () => {
    const weight = getCartNetWeight([
      { quantity: 1, weight_per_unit: 1, weight_uom: "Kg" },
      { quantity: 1, weight_per_unit: 500, weight_uom: "Gram" },
    ]);
    expect(weight.uom).toBe("");
    expect(weight.mixedUoms).toBe(true);
  });

  it("avoids floating point noise", () => {
    expect(getCartNetWeight([{ quantity: 3, weight_per_unit: 0.1 }]).total).toBe(0.3);
  });
});

describe("formatCartWeight", () => {
  it("shows the unit when there is one", () => {
    expect(formatCartWeight({ total: 12.5, uom: "Kg", mixedUoms: false })).toBe("12.5 Kg");
  });

  it("shows the bare number when units are mixed", () => {
    expect(formatCartWeight({ total: 3, uom: "", mixedUoms: true })).toBe("3");
  });
});
