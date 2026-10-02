import { describe, expect, it } from "vitest";
import {
  holdBlockedByMpesa,
  mpesaDraftKeptForStk,
  mpesaDraftToDiscard,
  mpesaOrderToRelease,
  normalizeMpesaStatus,
  resumedMpesaFlow,
  stkRetryAction,
} from "./mpesaDraftLifecycle";

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

describe("stkRetryAction", () => {
  const active = { method: "Mpesa-Sandbox-174379", amount: 4 };

  it("sends a new push for the current M-Pesa amount, so a discount since is respected", () => {
    expect(stkRetryAction(active, "0712345678", "254700000001")).toEqual({
      send: true,
      method: "Mpesa-Sandbox-174379",
      amount: 4,
      phone: "0712345678",
    });
  });

  it("falls back to the phone the failed push went to", () => {
    expect(stkRetryAction(active, "  ", "254700000001")).toMatchObject({ send: true, phone: "254700000001" });
  });

  it("asks for a phone when there is none to send to", () => {
    expect(stkRetryAction(active, "", undefined)).toEqual({
      send: false,
      reason: "Enter the customer's phone number to send the M-Pesa request again.",
    });
  });

  it("asks for an amount when no M-Pesa method has one", () => {
    expect(stkRetryAction(null, "0712345678", undefined)).toEqual({
      send: false,
      reason: "Enter an amount on an M-Pesa payment method before sending the request again.",
    });
    expect(stkRetryAction({ method: "Mpesa-Sandbox-174379", amount: 0 }, "0712345678", undefined)).toMatchObject({
      send: false,
    });
  });
});

describe("mpesaOrderToRelease", () => {
  it("hands the order to the server to delete or keep once nothing runs against it", () => {
    expect(mpesaOrderToRelease("SAL-ORD-9", 0)).toBe("SAL-ORD-9");
  });

  it("leaves it while a push or the submit is still running: the server cannot see the push yet", () => {
    expect(mpesaOrderToRelease("SAL-ORD-9", 1)).toBeNull();
  });

  it("has nothing to release without an order", () => {
    expect(mpesaOrderToRelease(null, 0)).toBeNull();
  });
});

describe("resumedMpesaFlow", () => {
  const request = {
    name: "MEXP-7",
    status: "Completed",
    amount: 4,
    phone_number: "254700000123",
    transaction_id: "UJ1TEST",
    checkout_request_id: "ws_CO_1",
    payment_gateway: "Mpesa-Sandbox-174379",
  };

  it("picks up the push the kept order was sent with, on the mode it went through", () => {
    expect(resumedMpesaFlow("SAL-ORD-9", request, ["Mpesa-111222", "Mpesa-Sandbox-174379"])).toEqual({
      modeOfPayment: "Mpesa-Sandbox-174379",
      amount: 4,
      phoneNumber: "254700000123",
      accountReference: "SAL-ORD-9",
      source: "stk",
      requestName: "MEXP-7",
      transactionId: "UJ1TEST",
      checkoutRequestId: "ws_CO_1",
      status: "completed",
      message: undefined,
    });
  });

  it("falls back to the first M-Pesa mode when the push's gateway is not one of the till's", () => {
    expect(resumedMpesaFlow("SAL-ORD-9", { ...request, payment_gateway: "Mpesa-Gone" }, ["Mpesa-111222"])?.modeOfPayment).toBe(
      "Mpesa-111222",
    );
  });

  it("carries a failed push's reason", () => {
    const flow = resumedMpesaFlow("SAL-ORD-9", { ...request, status: "Failed", result_desc: "DS timeout" }, ["Mpesa-111222"]);
    expect(flow).toMatchObject({ status: "failed", message: "DS timeout" });
  });

  it("has nothing to pick up without a push or an M-Pesa mode", () => {
    expect(resumedMpesaFlow("SAL-ORD-9", null, ["Mpesa-111222"])).toBeNull();
    expect(resumedMpesaFlow("SAL-ORD-9", request, [])).toBeNull();
  });
});

describe("normalizeMpesaStatus", () => {
  it.each([
    ["Completed", "completed"],
    ["Failed", "failed"],
    ["In Progress", "in_progress"],
    ["idle", "idle"],
  ])("%s is %s", (status, expected) => {
    expect(normalizeMpesaStatus(status)).toBe(expected);
  });
});
