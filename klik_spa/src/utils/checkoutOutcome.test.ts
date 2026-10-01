import { describe, expect, it } from "vitest";
import { checkoutWasQueued } from "./checkoutOutcome";

describe("checkoutWasQueued", () => {
  it("is false for a receipt-paid M-Pesa sale the server submitted directly, whatever the checkbox said", () => {
    // submit_draft_invoice's direct branch returns the submitted invoice itself.
    expect(checkoutWasQueued({ success: true, invoice_name: "POS-01567", invoice: { docstatus: 1, status: "Paid" } })).toBe(false);
  });

  it("is true for a draft the server queued for the worker", () => {
    expect(
      checkoutWasQueued({ success: true, queue_status: "Queued", invoice_name: "POS-1", invoice: { docstatus: 0, status: "Draft" } }),
    ).toBe(true);
  });

  it("reads the summary's status when the response carries no docstatus", () => {
    // _queue_sales_invoice answers with _get_invoice_response_summary: status, no docstatus.
    expect(checkoutWasQueued({ success: true, queue_status: "Queued", invoice: { status: "Draft" } })).toBe(true);
    expect(checkoutWasQueued({ success: true, invoice: { status: "Paid" } })).toBe(false);
  });

  it("trusts a replay's checkout_status over a stale queue_status", () => {
    // A directly submitted invoice still reads queue_status "Queued" (the field's default).
    expect(checkoutWasQueued({ checkout_status: "submitted", queue_status: "Queued" })).toBe(false);
    expect(checkoutWasQueued({ checkout_status: "processing" })).toBe(true);
  });

  it("falls back to whether the server reported a queue state at all", () => {
    expect(checkoutWasQueued({ success: true, queue_status: "Queued" })).toBe(true);
    expect(checkoutWasQueued({ success: true })).toBe(false);
    expect(checkoutWasQueued(null)).toBe(false);
  });
});
