import { describe, expect, it } from "vitest";
import { appliedFromReceipts, receiptCardState, uncoveredMpesa } from "./mpesaReceipts";
import type { MpesaRegisterPayment } from "../services/mpesa";

const p = (over: Partial<MpesaRegisterPayment>): MpesaRegisterPayment => ({
  name: "MPC2B-1",
  transamount: 10048,
  state: "new",
  open_amount: 10048,
  held_by: null,
  used_count: 0,
  selectable: true,
  ...over,
});

describe("receiptCardState", () => {
  it("an untouched receipt is new at its full amount", () => {
    expect(receiptCardState(p({}))).toMatchObject({ kind: "new", openAmount: 10048, selectable: true });
  });

  it("a part-used receipt of this customer is open at what is left", () => {
    expect(receiptCardState(p({ state: "open", open_amount: 5748, held_by: "Walk-in", used_count: 2 }))).toMatchObject({
      kind: "open",
      openAmount: 5748,
      total: 10048,
      usedCount: 2,
      selectable: true,
    });
  });

  it("another customer's receipt is other and not selectable", () => {
    expect(receiptCardState(p({ state: "open", open_amount: 700, held_by: "X", selectable: false }))).toMatchObject({
      kind: "other",
      heldBy: "X",
      selectable: false,
    });
  });

  it("an old server without open_amount falls back to transamount", () => {
    expect(receiptCardState({ name: "A", transamount: 250 } as MpesaRegisterPayment).openAmount).toBe(250);
  });
});

describe("appliedFromReceipts", () => {
  it("takes what the sale owes when the receipts hold more", () => {
    expect(appliedFromReceipts(10048, 3450)).toBe(3450);
  });

  it("takes all the receipts hold when the sale owes more", () => {
    expect(appliedFromReceipts(5748, 6548)).toBe(5748);
  });

  it("is never negative", () => {
    expect(appliedFromReceipts(100, -5)).toBe(0);
  });
});

describe("uncoveredMpesa", () => {
  it("is the M-Pesa amount no receipt or STK push covers", () => {
    expect(uncoveredMpesa(3450, 0, 0)).toBe(3450);
  });

  it("is zero when receipts cover it", () => {
    expect(uncoveredMpesa(3450, 10048, 0)).toBe(0);
  });

  it("counts a completed STK push", () => {
    expect(uncoveredMpesa(500, 200, 300)).toBe(0);
  });

  it("ignores sub-cent float noise", () => {
    expect(uncoveredMpesa(0.1 + 0.2, 0.3, 0)).toBe(0);
  });
});
