import { afterEach, describe, expect, it, vi } from "vitest";
import { discardMpesaDraft, DraftNoLongerDraftError, submitDraftInvoice } from "./salesInvoice";
import { HeldOrderGoneError } from "./salesOrder";

afterEach(() => vi.unstubAllGlobals());

const reply = (message: unknown) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ message }) });

describe("submitDraftInvoice", () => {
  it("raises a typed error when the invoice is no longer a draft", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal(
      "fetch",
      reply({ success: false, code: "not_draft", docstatus: 2, invoice_id: "POS-01190", error: "Cannot submit" }),
    );

    const err = await submitDraftInvoice("POS-01190").catch((e) => e);

    expect(err).toBeInstanceOf(DraftNoLongerDraftError);
    expect(err.invoiceId).toBe("POS-01190");
    expect(err.docstatus).toBe(2);
  });

  it("keeps a plain error for any other refusal", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal("fetch", reply({ success: false, error: "Stock is short" }));

    const err = await submitDraftInvoice("POS-01190").catch((e) => e);

    expect(err).not.toBeInstanceOf(DraftNoLongerDraftError);
    expect(err.message).toBe("Stock is short");
  });
});

describe("submitDraftInvoice for a held order paid by M-Pesa", () => {
  it("names the held order so the server finishes it", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    const fetch = reply({ success: true, invoice_name: "POS-01500" });
    vi.stubGlobal("fetch", fetch);

    await submitDraftInvoice("POS-01500", { items: [] }, "SAL-ORD-2026-00034");

    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body).toEqual({ invoice_id: "POS-01500", data: { items: [] }, held_order_id: "SAL-ORD-2026-00034" });
  });

  it("sends the remarks on their own, even with no cart data", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    const fetch = reply({ success: true, invoice_name: "POS-01500" });
    vi.stubGlobal("fetch", fetch);

    await submitDraftInvoice("POS-01500", undefined, null, "");

    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ invoice_id: "POS-01500", remarks: "" });
  });

  it("sends no held order for an ordinary draft", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    const fetch = reply({ success: true, invoice_name: "POS-01500" });
    vi.stubGlobal("fetch", fetch);

    await submitDraftInvoice("POS-01500");

    expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty("held_order_id");
  });

  it("raises HeldOrderGoneError when the held order was finished elsewhere", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal(
      "fetch",
      reply({ success: false, code: "held_order_gone", order_id: "SAL-ORD-2026-00034", message: "gone" }),
    );

    const err = await submitDraftInvoice("POS-01500", undefined, "SAL-ORD-2026-00034").catch((e) => e);

    expect(err).toBeInstanceOf(HeldOrderGoneError);
    expect(err.orderId).toBe("SAL-ORD-2026-00034");
  });
});

describe("discardMpesaDraft", () => {
  it("reports a discarded draft", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal("fetch", reply({ success: true }));

    expect(await discardMpesaDraft("POS-01500")).toEqual({ kept: false });
  });

  it("reports a draft kept because an STK push was sent from it", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal(
      "fetch",
      reply({ success: false, code: "mpesa_request_sent", invoice_id: "POS-01500", error: "Draft POS-01500 was kept" }),
    );

    expect(await discardMpesaDraft("POS-01500")).toEqual({ kept: true, message: "Draft POS-01500 was kept" });
  });

  it("raises on any other refusal", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    vi.stubGlobal("fetch", reply({ success: false, error: "not this checkout's to discard" }));

    const err = await discardMpesaDraft("POS-01500").catch((e) => e);

    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("not this checkout's to discard");
  });
});
