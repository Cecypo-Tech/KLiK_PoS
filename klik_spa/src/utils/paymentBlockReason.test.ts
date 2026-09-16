import { describe, expect, it } from "vitest";
import { paymentBlockReason, type PaymentBlockState } from "./paymentBlockReason";

const ready: PaymentBlockState = {
  invoiceSubmitted: false,
  isProcessingPayment: false,
  reconciliationOk: true,
  reconciliationMessage: null,
  isCreditSale: false,
  hasDueDate: false,
  isB2C: true,
  outstandingAmount: 0,
  outstandingLabel: "KSh 0.00",
  alreadySubmittedAs: null,
  priceApprovalMessage: null,
};

describe("paymentBlockReason", () => {
  it("is null when the sale can be submitted", () => {
    expect(paymentBlockReason(ready)).toBeNull();
  });

  it("says a submitted invoice is already done", () => {
    expect(paymentBlockReason({ ...ready, invoiceSubmitted: true })).toMatch(/already submitted/);
  });

  it("blocks a sale already recorded as another invoice", () => {
    expect(paymentBlockReason({ ...ready, alreadySubmittedAs: "POS-01190" })).toMatch(/POS-01190/);
  });

  it("blocks a held order that still needs price approval", () => {
    expect(
      paymentBlockReason({ ...ready, priceApprovalMessage: "Wait for approval on the held order." }),
    ).toBe("Wait for approval on the held order.");
  });

  it("still prefers the already-submitted duplicate check over price approval", () => {
    expect(
      paymentBlockReason({
        ...ready,
        alreadySubmittedAs: "POS-01190",
        priceApprovalMessage: "Wait for approval on the held order.",
      }),
    ).toMatch(/POS-01190/);
  });

  it("says a payment is in progress", () => {
    expect(paymentBlockReason({ ...ready, isProcessingPayment: true })).toMatch(/already being processed/);
  });

  it("repeats the price check's own message", () => {
    expect(
      paymentBlockReason({ ...ready, reconciliationOk: false, reconciliationMessage: "Line 2 was repriced" }),
    ).toBe("Line 2 was repriced");
  });

  it("asks for a due date on a credit sale", () => {
    expect(paymentBlockReason({ ...ready, isCreditSale: true })).toMatch(/due date/);
    expect(paymentBlockReason({ ...ready, isCreditSale: true, hasDueDate: true })).toBeNull();
  });

  it("names what is still to be paid on a cash sale", () => {
    expect(
      paymentBlockReason({ ...ready, outstandingAmount: 150, outstandingLabel: "KSh 150.00" }),
    ).toBe("KSh 150.00 still to be paid");
  });

  it("does not ask a B2B or credit sale to be paid in full", () => {
    expect(paymentBlockReason({ ...ready, isB2C: false, outstandingAmount: 150 })).toBeNull();
    expect(
      paymentBlockReason({ ...ready, isCreditSale: true, hasDueDate: true, outstandingAmount: 150 }),
    ).toBeNull();
  });
});
