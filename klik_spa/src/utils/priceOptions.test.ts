import { describe, it, expect } from "vitest";
import { buildPriceOptions, cyclePriceOptionIndex } from "./priceOptions";

describe("buildPriceOptions", () => {
  it("maps each price list entry to an option", () => {
    const options = buildPriceOptions(
      [
        { price_list: "Retail", rate: 450 },
        { price_list: "Wholesale", rate: 400 },
      ],
      false,
      450
    );
    expect(options).toEqual([
      { label: "Retail", rate: 450 },
      { label: "Wholesale", rate: 400 },
    ]);
  });

  it("appends a custom-price option when rate change is allowed", () => {
    const options = buildPriceOptions([{ price_list: "Retail", rate: 450 }], true, 450);
    expect(options).toHaveLength(2);
    expect(options[1]).toEqual({ label: "Custom Price", rate: 450, isCustom: true });
  });

  it("omits the custom-price option when rate change is not allowed", () => {
    const options = buildPriceOptions([{ price_list: "Retail", rate: 450 }], false, 450);
    expect(options).toHaveLength(1);
    expect(options.some((o) => o.isCustom)).toBe(false);
  });

  it("still offers a custom option with no price lists at all, when allowed", () => {
    const options = buildPriceOptions([], true, 99);
    expect(options).toEqual([{ label: "Custom Price", rate: 99, isCustom: true }]);
  });

  it("returns an empty list with no price lists and no rate-change permission", () => {
    expect(buildPriceOptions([], false, 99)).toEqual([]);
  });
});

describe("cyclePriceOptionIndex", () => {
  it("moves forward", () => {
    expect(cyclePriceOptionIndex(0, 3, 1)).toBe(1);
  });

  it("moves backward", () => {
    expect(cyclePriceOptionIndex(1, 3, -1)).toBe(0);
  });

  it("wraps forward past the end", () => {
    expect(cyclePriceOptionIndex(2, 3, 1)).toBe(0);
  });

  it("wraps backward past the start", () => {
    expect(cyclePriceOptionIndex(0, 3, -1)).toBe(2);
  });

  it("returns 0 for an empty option list rather than dividing by zero", () => {
    expect(cyclePriceOptionIndex(0, 0, 1)).toBe(0);
  });
});
