import { describe, expect, it } from "vitest";
import { resumedMpesaFlow } from "./mpesaDraftLifecycle";
import {
  autoCheckFor,
  pretickedReceipt,
  pushCheckMessage,
  receiptLookupStep,
  RECEIPT_PENDING_MESSAGE,
  stkReceiptPending,
} from "./stkPushCheck";

const waiting = { source: "stk" as const, status: "in_progress" as const, requestName: "MEXP-1" };

describe("stkReceiptPending", () => {
  it("is a push Safaricom says is paid, with no receipt number yet", () => {
    expect(stkReceiptPending({ ...waiting, status: "completed" })).toBe(true);
  });

  it("is not a confirmed push, a waiting or failed one, nor picked receipts", () => {
    expect(stkReceiptPending({ ...waiting, status: "completed", transactionId: "UJ1TEST" })).toBe(false);
    expect(stkReceiptPending(waiting)).toBe(false);
    expect(stkReceiptPending({ ...waiting, status: "failed" })).toBe(false);
    expect(stkReceiptPending({ source: "c2b", status: "completed" })).toBe(false);
    expect(stkReceiptPending(null)).toBe(false);
  });

  it("is how a paid order without its receipt comes back from Held", () => {
    const push = { name: "MEXP-7", status: "Completed", amount: 450, transaction_id: null };
    expect(stkReceiptPending(resumedMpesaFlow("SAL-ORD-9", push, ["Mpesa-111222"]))).toBe(true);
  });
});

describe("autoCheckFor", () => {
  it("checks a waiting push once", () => {
    expect(autoCheckFor(waiting, null)).toBe("MEXP-1");
    expect(autoCheckFor(waiting, "MEXP-1")).toBeNull();
  });

  it("checks a new push even after an earlier one was checked", () => {
    expect(autoCheckFor(waiting, "MEXP-0")).toBe("MEXP-1");
  });

  it("never checks a push that is no longer waiting, or receipts", () => {
    expect(autoCheckFor({ ...waiting, status: "completed" }, null)).toBeNull();
    expect(autoCheckFor({ ...waiting, status: "failed" }, null)).toBeNull();
    expect(autoCheckFor({ source: "c2b", status: "in_progress" }, null)).toBeNull();
    expect(autoCheckFor(null, null)).toBeNull();
  });
});

describe("receiptLookupStep", () => {
  it("asks for a pull at once, then at 30 s and at 90 s - three in all", () => {
    expect(receiptLookupStep(0, 0).pull).toBe(true);
    expect(receiptLookupStep(5_000, 1).pull).toBe(false);
    expect(receiptLookupStep(30_000, 1).pull).toBe(true);
    expect(receiptLookupStep(60_000, 2).pull).toBe(false);
    expect(receiptLookupStep(90_000, 2).pull).toBe(true);
    expect(receiptLookupStep(115_000, 3).pull).toBe(false);
  });

  it("gives up two minutes in", () => {
    expect(receiptLookupStep(115_000, 3).giveUp).toBe(false);
    expect(receiptLookupStep(120_000, 3).giveUp).toBe(true);
  });
});

describe("pretickedReceipt", () => {
  it("ticks the only match", () => {
    expect(pretickedReceipt([{ name: "R1" }])).toEqual({ name: "R1" });
  });

  it("ticks none of several, or of none", () => {
    expect(pretickedReceipt([{ name: "R1" }, { name: "R2" }])).toBeNull();
    expect(pretickedReceipt([])).toBeNull();
  });
});

describe("pushCheckMessage", () => {
  it("says what Safaricom answered", () => {
    expect(pushCheckMessage({ outcome: "paid" })).toBe(RECEIPT_PENDING_MESSAGE);
    expect(pushCheckMessage({ outcome: "paid", transaction_id: "UJ1TEST" })).toBe("Payment confirmed");
    expect(pushCheckMessage({ outcome: "not_paid", reason: "Request cancelled by user" })).toBe("Request cancelled by user");
    expect(pushCheckMessage({ outcome: "waiting" })).toBe("The customer is still being asked - check again shortly.");
    expect(pushCheckMessage({ outcome: "no_answer" })).toBe("Couldn't get an answer from Safaricom - try again.");
  });
});
