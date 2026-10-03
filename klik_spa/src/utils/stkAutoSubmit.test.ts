import { describe, expect, it } from "vitest";
import { canSendStk, nextAllocationTargets, stkAutoSubmitDecision } from "./stkAutoSubmit";

describe("stkAutoSubmitDecision", () => {
  const ready = { blockReason: null, isProcessing: false, invoiceSubmitted: false };

  it("submits the sale the moment a paid push leaves nothing else to do", () => {
    expect(stkAutoSubmitDecision(ready)).toEqual({ action: "submit" });
  });

  it("does not guess when something still blocks the submit - it says what", () => {
    expect(stkAutoSubmitDecision({ ...ready, blockReason: "Enter the remaining Sh 70.00." })).toEqual({
      action: "notify",
      reason: "Enter the remaining Sh 70.00.",
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
