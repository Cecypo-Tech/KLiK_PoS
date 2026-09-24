import { describe, it, expect } from "vitest";
import { returnNotice } from "./returnNotice";

describe("returnNotice", () => {
  it("reports a load failure as a load failure, never as 'all returned'", () => {
    // Regression: a cashier refused the invoice ("rung by another cashier") saw
    // "All items from this invoice have already been returned" and went looking
    // for a credit note that did not exist.
    expect(returnNotice([], "This invoice was rung by another cashier.")).toBe("load-error");
  });

  it("says 'all returned' only when every loaded row has nothing left", () => {
    expect(returnNotice([{ available_qty: 0 }, { available_qty: 0 }], null)).toBe("all-returned");
  });

  it("says nothing while something is still returnable", () => {
    expect(returnNotice([{ available_qty: 0 }, { available_qty: 2 }], null)).toBeNull();
  });

  it("says nothing for an empty list that did not fail to load", () => {
    expect(returnNotice([], null)).toBeNull();
  });
});
