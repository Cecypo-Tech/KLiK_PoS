import { describe, expect, it } from "vitest";

import { authorisationStillValid, checkoutPriceList, floorBlockMessage, floorRowsKey, type FloorRow } from "./priceFloor";

const row = (over: Partial<FloorRow> = {}): FloorRow => ({
  idx: 1,
  item_code: "H4",
  item_name: "H4 Bulb",
  uom: "Nos",
  qty: 1,
  rate: 420,
  minimum: 450,
  price_list: "Retail",
  ...over,
});

describe("checkoutPriceList", () => {
  it("sends the cart's list when the till lets the cashier switch lists", () => {
    expect(checkoutPriceList({ allow_price_list_switching: 1 }, "Distributor")).toBe("Distributor");
  });

  it("sends nothing when switching is off, so the server keeps its own chain", () => {
    expect(checkoutPriceList({ allow_price_list_switching: 0 }, "Distributor")).toBeNull();
    expect(checkoutPriceList(null, "Distributor")).toBeNull();
  });

  it("sends nothing when no list is selected", () => {
    expect(checkoutPriceList({ allow_price_list_switching: 1 }, null)).toBeNull();
  });
});

describe("supervisor authorisation", () => {
  it("still covers the same below-minimum lines", () => {
    const auth = { token: "t", key: floorRowsKey([row()]) };
    expect(authorisationStillValid(auth, [row()])).toBe(true);
  });

  it("no longer covers a lowered price", () => {
    const auth = { token: "t", key: floorRowsKey([row()]) };
    expect(authorisationStillValid(auth, [row({ rate: 410 })])).toBe(false);
  });

  it("no longer covers a raised quantity or another line going below", () => {
    const auth = { token: "t", key: floorRowsKey([row()]) };
    expect(authorisationStillValid(auth, [row({ qty: 2 })])).toBe(false);
    expect(authorisationStillValid(auth, [row(), row({ idx: 2, item_code: "H7" })])).toBe(false);
  });

  it("does not depend on the order the server lists lines in", () => {
    const a = row();
    const b = row({ idx: 2, item_code: "H7" });
    expect(floorRowsKey([a, b])).toBe(floorRowsKey([b, a]));
  });

  it("is never valid without an authorisation", () => {
    expect(authorisationStillValid(null, [row()])).toBe(false);
  });
});

describe("floorBlockMessage", () => {
  it("blocks payment while a line is below its minimum and nobody authorised it", () => {
    expect(floorBlockMessage({ enforced: true, rows: [row()] }, null)).toBe(
      "Prices below the minimum - fix them or ask a supervisor to authorise"
    );
  });

  it("lets payment through once a supervisor authorised these lines", () => {
    expect(floorBlockMessage({ enforced: true, rows: [row()] }, { token: "t", key: floorRowsKey([row()]) })).toBeNull();
  });

  it("does not block a till that does not enforce, or a clean cart", () => {
    expect(floorBlockMessage({ enforced: false, rows: [] }, null)).toBeNull();
    expect(floorBlockMessage({ enforced: true, rows: [] }, null)).toBeNull();
    expect(floorBlockMessage(null, null)).toBeNull();
  });
});
