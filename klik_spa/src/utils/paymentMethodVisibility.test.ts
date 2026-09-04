import { describe, it, expect } from "vitest";
import { partitionPaymentMethods, type RankedMethod } from "./paymentMethodVisibility";

const m = (id: string, idx: number, isDefault = false, amount = 0): RankedMethod =>
  ({ id, idx, isDefault, amount });

const ids = (list: RankedMethod[]) => list.map((x) => x.id);

describe("partitionPaymentMethods", () => {
  it("shows everything and offers no tags when there are three or fewer", () => {
    const methods = [m("cash", 1, true), m("mpesa", 2), m("card", 3)];
    const { rows, tags } = partitionPaymentMethods(methods, []);
    expect(ids(rows)).toEqual(["cash", "mpesa", "card"]);
    expect(tags).toEqual([]);
  });

  it("keeps the first three by idx and tags the rest", () => {
    const methods = [m("cash", 1, true), m("mpesa1", 2), m("mpesa2", 3), m("cheque", 4), m("card", 5)];
    const { rows, tags } = partitionPaymentMethods(methods, []);
    expect(ids(rows)).toEqual(["cash", "mpesa1", "mpesa2"]);
    expect(ids(tags)).toEqual(["cheque", "card"]);
  });

  it("always keeps the default as a row even when it sorts late", () => {
    // default is 5th; it displaces the third slot, so three rows total, in idx order.
    const methods = [m("a", 1), m("b", 2), m("c", 3), m("d", 4), m("cash", 5, true)];
    const { rows, tags } = partitionPaymentMethods(methods, []);
    expect(ids(rows)).toEqual(["a", "b", "cash"]);
    expect(ids(tags)).toEqual(["c", "d"]);
  });

  it("keeps a method with an amount as a row so a split payment cannot collapse", () => {
    const methods = [m("cash", 1, true), m("mpesa1", 2), m("mpesa2", 3), m("cheque", 4, false, 250)];
    const { rows, tags } = partitionPaymentMethods(methods, []);
    expect(ids(rows)).toEqual(["cash", "mpesa1", "mpesa2", "cheque"]);
    expect(tags).toEqual([]);
  });

  it("appends promoted methods in the order they were promoted", () => {
    const methods = [m("cash", 1, true), m("mpesa1", 2), m("mpesa2", 3), m("cheque", 4), m("card", 5)];
    const { rows, tags } = partitionPaymentMethods(methods, ["card", "cheque"]);
    expect(ids(rows)).toEqual(["cash", "mpesa1", "mpesa2", "card", "cheque"]);
    expect(tags).toEqual([]);
  });

  it("does not reorder the existing rows when something is promoted", () => {
    const methods = [m("cash", 1, true), m("mpesa1", 2), m("mpesa2", 3), m("cheque", 4)];
    const before = ids(partitionPaymentMethods(methods, []).rows);
    const after = ids(partitionPaymentMethods(methods, ["cheque"]).rows);
    expect(after.slice(0, before.length)).toEqual(before);
  });

  it("ignores a promoted id that is not a known method", () => {
    const methods = [m("cash", 1, true), m("mpesa1", 2), m("mpesa2", 3), m("cheque", 4)];
    const { rows } = partitionPaymentMethods(methods, ["ghost"]);
    expect(ids(rows)).toEqual(["cash", "mpesa1", "mpesa2"]);
  });
});
