import { describe, it, expect } from "vitest";
import { buildPriceOptions, computePricePopupPosition, cyclePriceOptionIndex, resolveActivePriceList } from "./priceOptions";

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

describe("computePricePopupPosition", () => {
  const viewport = { width: 1280, height: 720 };

  it("opens below the anchor when there is room", () => {
    const pos = computePricePopupPosition({ left: 100, top: 200, bottom: 220 }, 3, viewport);
    expect(pos).toEqual({ left: 100, top: 226 });
  });

  it("flips above the anchor when the popup would run off the bottom", () => {
    const pos = computePricePopupPosition({ left: 100, top: 650, bottom: 670 }, 3, viewport);
    expect(pos).toEqual({ left: 100, bottom: 76 });
  });

  it("keeps the popup inside the right edge of the viewport", () => {
    const pos = computePricePopupPosition({ left: 1200, top: 200, bottom: 220 }, 1, viewport);
    expect(pos.left).toBe(1280 - 224 - 8);
  });

  it("never positions left of the viewport gutter on a narrow screen", () => {
    const pos = computePricePopupPosition({ left: 50, top: 10, bottom: 30 }, 1, { width: 200, height: 720 });
    expect(pos.left).toBe(8);
  });
});

describe("resolveActivePriceList", () => {
  it("prefers the price list picked on the cart", () => {
    expect(resolveActivePriceList("Elite", "Wholesale", "Retail")).toBe("Elite");
  });

  it("falls back to the customer's price list, then the POS Profile's", () => {
    expect(resolveActivePriceList(null, "Wholesale", "Retail")).toBe("Wholesale");
    expect(resolveActivePriceList("", undefined, "Retail")).toBe("Retail");
  });

  it("is empty when nothing is configured", () => {
    expect(resolveActivePriceList(null, undefined, undefined)).toBe("");
  });
});
