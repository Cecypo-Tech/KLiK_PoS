import { describe, expect, it } from "vitest";
import { canSendStk, nextAllocationTargets, stkAutoSubmitDecision } from "./stkAutoSubmit";

describe("stkAutoSubmitDecision", () => {
  // The paid push alone covers the server's total, nothing else is tendered or blocking.
  const ready = {
    blockReason: null,
    isProcessing: false,
    invoiceSubmitted: false,
    previewReady: true,
    paidAmount: 430,
    payable: 430,
    otherRowsTendered: false,
  };

  it("submits when the paid push alone covers the sale", () => {
    expect(stkAutoSubmitDecision(ready)).toEqual({ action: "submit" });
  });

  it("waits for the server's total before deciding anything", () => {
    expect(stkAutoSubmitDecision({ ...ready, previewReady: false })).toEqual({ action: "wait" });
  });

  it("never submits other rows the cashier has not confirmed (a split or a pre-filled cash row)", () => {
    expect(stkAutoSubmitDecision({ ...ready, payable: 1000, paidAmount: 600, otherRowsTendered: true })).toEqual({
      action: "notify",
      reason: "other_rows",
    });
  });

  it("says what is still to pay when the push covers only part of the sale", () => {
    expect(stkAutoSubmitDecision({ ...ready, payable: 1000, paidAmount: 600 })).toEqual({
      action: "notify",
      reason: "short",
    });
  });

  it("does not guess when something else still blocks the submit - it passes the reason on", () => {
    expect(stkAutoSubmitDecision({ ...ready, blockReason: "Select a due date for this credit sale" })).toEqual({
      action: "notify",
      reason: "blocked",
      detail: "Select a due date for this credit sale",
    });
  });

  it("leaves a submit already running alone", () => {
    expect(stkAutoSubmitDecision({ ...ready, isProcessing: true })).toEqual({ action: "none" });
  });

  it("does nothing once the sale is submitted", () => {
    expect(stkAutoSubmitDecision({ ...ready, invoiceSubmitted: true })).toEqual({ action: "none" });
  });
});

describe("canSendStk", () => {
  it("sends when nothing is pending or paid", () => {
    expect(canSendStk({ isProcessing: false, stkPending: false, stkPaid: false })).toBe(true);
  });

  it("never rings the customer twice or again after paying", () => {
    expect(canSendStk({ isProcessing: false, stkPending: true, stkPaid: false })).toBe(false);
    expect(canSendStk({ isProcessing: false, stkPending: false, stkPaid: true })).toBe(false);
    expect(canSendStk({ isProcessing: true, stkPending: false, stkPaid: false })).toBe(false);
  });
});

describe("nextAllocationTargets", () => {
  it("re-apportions every later method when nothing is locked", () => {
    expect(nextAllocationTargets(["Cash", "Mpesa", "Card"], "Cash", null)).toEqual(["Mpesa", "Card"]);
  });

  it("never resets a paid M-Pesa row when an earlier row changes", () => {
    expect(nextAllocationTargets(["Cash", "Mpesa", "Card"], "Cash", "Mpesa")).toEqual(["Card"]);
  });

  it("has nothing to re-apportion for an unknown method", () => {
    expect(nextAllocationTargets(["Cash", "Mpesa"], "Gift", null)).toEqual([]);
  });
});
