import { describe, expect, it } from "vitest";
import { appliedFromReceipts, isMpesaPaymentMode, receiptCardState, receiptDraftSubmitData, uncoveredMpesa } from "./mpesaReceipts";
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

describe("receiptDraftSubmitData", () => {
  const data = (amounts: number[]) => ({ customer: "Walk In", paymentMethods: amounts.map((amount) => ({ method: "Cash", amount })) });

  it("sends the other payment rows when the cashier took money besides the receipts", () => {
    const d = data([800]);
    expect(receiptDraftSubmitData(d)).toBe(d);
  });

  it("sends nothing when the receipts pay the whole sale, so the draft keeps what it has", () => {
    // An empty payments list would be refused as "a cash sale with no payment".
    expect(receiptDraftSubmitData(data([]))).toBeUndefined();
    expect(receiptDraftSubmitData(data([0]))).toBeUndefined();
  });
});

describe("isMpesaPaymentMode", () => {
  it("follows the server's flag when it sends one", () => {
    expect(isMpesaPaymentMode({ is_mpesa: true, type: "Bank" }, "Collections")).toBe(true);
    // A Bank-type mode that merely has M-Pesa in its name is not held to a receipt.
    expect(isMpesaPaymentMode({ is_mpesa: false, type: "Bank" }, "KCB Mpesa")).toBe(false);
  });

  it("falls back to type Phone or the name for an older server", () => {
    expect(isMpesaPaymentMode({ type: "Phone" }, "Till 1")).toBe(true);
    expect(isMpesaPaymentMode(undefined, "Mpesa-160745")).toBe(true);
    expect(isMpesaPaymentMode({ type: "Cash" }, "Cash")).toBe(false);
  });
});
