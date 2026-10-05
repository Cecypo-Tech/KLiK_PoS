import { describe, expect, it } from "vitest";
import { appliedFromReceipts, isMpesaPaymentMode, receiptCardState, receiptPicksPayload, receiptLeftoverMessage, receiptPaidAt, refitReceiptRow, tenderSent, uncoveredMpesa } from "./mpesaReceipts";
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

describe("receiptPicksPayload", () => {
  it("carries the picked receipts and their mode to the submit", () => {
    expect(
      receiptPicksPayload({ source: "c2b", modeOfPayment: "Mpesa-1", c2bPayments: [{ name: "R1" }, { name: "R2" }] }),
    ).toEqual({ mode_of_payment: "Mpesa-1", payments: ["R1", "R2"] });
  });

  it("carries nothing for an STK push or before any pick", () => {
    expect(receiptPicksPayload(null)).toBeNull();
    expect(receiptPicksPayload({ source: "stk", modeOfPayment: "Mpesa-1" })).toBeNull();
    expect(receiptPicksPayload({ source: "c2b", modeOfPayment: "Mpesa-1", c2bPayments: [] })).toBeNull();
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

describe("receiptLeftoverMessage", () => {
  it("says the money stays on the receipt for the customer's next sale, in the sale's currency", () => {
    expect(receiptLeftoverMessage(6598, "Sh", "Walk In")).toBe(
      "Sh 6,598.00 stays on the M-Pesa receipt for Walk In's next sale. No cash change is given for M-Pesa.",
    );
  });
});

describe("receiptPaidAt", () => {
  it("reads Safaricom's transtime as the payment date and time", () => {
    expect(receiptPaidAt({ transtime: "20261005125701", posting_date: "2026-10-04" }, "2026-10-05")).toEqual({
      label: "Oct 5, 2026 12:57",
      today: true,
    });
  });

  it("marks a receipt from an earlier day as not today", () => {
    expect(receiptPaidAt({ transtime: "20260618173837" }, "2026-10-05")?.today).toBe(false);
  });

  it("falls back to the posting date when transtime is not a full timestamp", () => {
    expect(receiptPaidAt({ transtime: "120000", posting_date: "2026-10-05" }, "2026-10-05")).toEqual({
      label: "Oct 5, 2026",
      today: true,
    });
  });

  it("shows nothing without either", () => {
    expect(receiptPaidAt({}, "2026-10-05")).toBeNull();
  });
});

describe("tenderSent", () => {
  const rows = [
    { method: "Cash", amount: 200 },
    { method: "Mpesa-1", amount: 770 },
  ];

  it("leaves out the M-Pesa row the picked receipts pay as advances", () => {
    expect(tenderSent(rows, "Mpesa-1")).toEqual([{ method: "Cash", amount: 200 }]);
  });

  it("sends every row when no receipts were picked", () => {
    expect(tenderSent(rows, null)).toEqual(rows);
  });
});

describe("refitReceiptRow", () => {
  it("shrinks the receipts' row, not the cash, when a voucher is added", () => {
    expect(refitReceiptRow({ Cash: 200, "Mpesa-1": 800, voucher: 300 }, "Mpesa-1", 5000, 1000)).toEqual({
      Cash: 200,
      "Mpesa-1": 500,
      voucher: 300,
    });
  });

  it("gives the row back, up to what the receipts hold, when the voucher goes", () => {
    expect(refitReceiptRow({ Cash: 200, "Mpesa-1": 500, voucher: 0 }, "Mpesa-1", 600, 1000)).toEqual({
      Cash: 200,
      "Mpesa-1": 600,
      voucher: 0,
    });
  });

  it("never goes below nothing when the other rows already pay the sale", () => {
    expect(refitReceiptRow({ Cash: 1200, "Mpesa-1": 300 }, "Mpesa-1", 5000, 1000)["Mpesa-1"]).toBe(0);
  });
});
