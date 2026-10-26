import { describe, expect, it } from "vitest";
import { lineInUom, nextUom, switchUom, uomMaps } from "./uomSwitch";

// Binding wire: sold by the roll (stock UOM) or by the kg; a roll is 15 kg.
const maps = uomMaps({
  base_uom: "Roll(s)",
  uoms: [
    { uom: "Roll(s)", conversion_factor: 1, price: 3000 },
    { uom: "kg(s)", conversion_factor: 1 / 15, price: 201 },
    { uom: "Coil", conversion_factor: 0.5, price: 0 },
  ],
});

describe("uomMaps", () => {
  it("lists each unit once, with its price and factor", () => {
    expect(maps.uoms).toEqual(["Roll(s)", "kg(s)", "Coil"]);
    expect(maps.factors["kg(s)"]).toBeCloseTo(1 / 15);
    expect(uomMaps({ base_uom: "Nos", uoms: [] }).factors).toEqual({ Nos: 1 });
  });
});

describe("nextUom", () => {
  it("cycles through the units and wraps", () => {
    expect(nextUom(maps.uoms, "Roll(s)")).toBe("kg(s)");
    expect(nextUom(maps.uoms, "Coil")).toBe("Roll(s)");
  });
  it("has nowhere to go with one unit", () => {
    expect(nextUom(["Nos"], "Nos")).toBeNull();
  });
});

describe("switchUom", () => {
  it("takes the unit's own price", () => {
    expect(switchUom(maps, "Roll(s)", 3000, "kg(s)")).toEqual({
      uom: "kg(s)",
      price: 201,
      conversionFactor: maps.factors["kg(s)"],
    });
  });
  it("converts the current price through the stock unit when the unit has no price", () => {
    expect(switchUom(maps, "kg(s)", 201, "Coil").price).toBeCloseTo(201 * 15 * 0.5);
  });
});

describe("lineInUom", () => {
  it("moves the line's stock figure into the new unit", () => {
    const line = { uom: "Roll(s)", price: 3000, conversion_factor: 1, available: 100 };
    expect(lineInUom(line, "kg(s)", 201, 1 / 15)).toEqual({ uom: "kg(s)", price: 201, conversion_factor: 1 / 15, available: 1500 });
  });
  it("keeps the factor and stock when no factor is given", () => {
    const line = { uom: "Nos", price: 5, available: 7 };
    expect(lineInUom(line, "Nos", 6)).toEqual({ uom: "Nos", price: 6, available: 7 });
  });
});
