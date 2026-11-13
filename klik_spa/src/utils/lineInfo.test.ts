import { describe, expect, it } from "vitest";
import { uomLines, visibleFacts, type LineInfo } from "./lineInfo";

const info: LineInfo = {
  rows: [
    { key: "description", label: "Description", value: "Tonic water" },
    { key: "in_stock", label: "In stock" },
    { key: "valuation", label: "Valuation" },
    { key: "margin", label: "Margin" },
    { key: "custom_pack_size", label: "Pack Size", value: "24" },
  ],
  warehouses: [],
  uoms: [{ uom: "Box", conversion_factor: 24 }],
  stock_uom: "Nos",
};

describe("visibleFacts", () => {
  it("keeps the till's order", () => {
    expect(visibleFacts(info, false).map((r) => r.key)).toEqual(["description", "in_stock", "valuation", "margin", "custom_pack_size"]);
  });
  it("drops the cost facts when the till hides cost", () => {
    expect(visibleFacts(info, true).map((r) => r.key)).toEqual(["description", "in_stock", "custom_pack_size"]);
  });
  it("nothing before the info arrives", () => {
    expect(visibleFacts(null, false)).toEqual([]);
  });
});

describe("uomLines", () => {
  it("one line per other unit, in the stock unit", () => {
    expect(uomLines(info)).toEqual(["1 Box = 24 Nos"]);
  });
});
