import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftNoLongerDraftError, submitDraftInvoice } from "./salesInvoice";

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
