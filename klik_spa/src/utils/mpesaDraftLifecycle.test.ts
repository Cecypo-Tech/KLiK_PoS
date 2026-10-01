import { describe, expect, it } from "vitest";
import { holdBlockedByMpesa, mpesaDraftKeptForStk, mpesaDraftToDiscard } from "./mpesaDraftLifecycle";

const none = new Set<string>();

describe("mpesaDraftToDiscard", () => {
  it("discards an idle draft no STK push was sent from", () => {
    expect(mpesaDraftToDiscard({ draftName: "POS-1", workInFlight: 0, stkSentFrom: none })).toBe("POS-1");
  });

  it("has nothing to discard without a draft", () => {
    expect(mpesaDraftToDiscard({ draftName: null, workInFlight: 0, stkSentFrom: none })).toBeNull();
  });

  it("keeps a draft while an STK push, a reconcile or the submit is still running against it", () => {
    // The STK request is committed only after Safaricom accepts it, so the server cannot
    // see it yet: the phone may already be ringing.
    expect(mpesaDraftToDiscard({ draftName: "POS-1", workInFlight: 1, stkSentFrom: none })).toBeNull();
  });

  it("keeps a draft an STK push was sent from, whatever became of it", () => {
    expect(mpesaDraftToDiscard({ draftName: "POS-1", workInFlight: 0, stkSentFrom: new Set(["POS-1"]) })).toBeNull();
  });

  it("is not stopped by a push sent from another draft", () => {
    expect(mpesaDraftToDiscard({ draftName: "POS-2", workInFlight: 0, stkSentFrom: new Set(["POS-1"]) })).toBe("POS-2");
  });
});

describe("holdBlockedByMpesa", () => {
  it("lets an order with no M-Pesa request be held", () => {
    expect(holdBlockedByMpesa(null)).toBeNull();
    expect(holdBlockedByMpesa({ source: "c2b", status: "completed" })).toBeNull();
  });

  it("refuses while an STK push is waiting on the customer", () => {
    expect(holdBlockedByMpesa({ source: "stk", status: "in_progress" })).toMatch(/waiting/i);
  });

  it("refuses once the customer has paid by STK - holding would charge them twice", () => {
    expect(holdBlockedByMpesa({ source: "stk", status: "completed" })).toMatch(/paid/i);
  });

  it("lets the order be held after the push failed", () => {
    expect(holdBlockedByMpesa({ source: "stk", status: "failed" })).toBeNull();
  });
});

describe("mpesaDraftKeptForStk", () => {
  it("names the draft kept because an STK push was sent from it, so the cashier is told", () => {
    const message = mpesaDraftKeptForStk({ draftName: "POS-1", workInFlight: 0, stkSentFrom: new Set(["POS-1"]) });
    expect(message).toContain("POS-1");
    expect(message).toMatch(/M-Pesa/);
  });

  it("says nothing for a draft that is discarded, or kept only while work is running", () => {
    expect(mpesaDraftKeptForStk({ draftName: "POS-1", workInFlight: 0, stkSentFrom: none })).toBeNull();
    expect(mpesaDraftKeptForStk({ draftName: null, workInFlight: 0, stkSentFrom: new Set(["POS-1"]) })).toBeNull();
  });
});
