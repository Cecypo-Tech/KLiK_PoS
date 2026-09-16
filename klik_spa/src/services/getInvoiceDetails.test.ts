import { afterEach, describe, expect, it, vi } from "vitest";
import { getInvoiceDetails } from "./salesInvoice";

afterEach(() => vi.unstubAllGlobals());

const reply = (message: unknown) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ message }) });

describe("getInvoiceDetails", () => {
  it("passes a refusal on as a failure with its reason", async () => {
    vi.stubGlobal("fetch", reply({ success: false, code: "forbidden", error: "Rung by another cashier." }));
    expect(await getInvoiceDetails("POS-1")).toEqual({ success: false, error: "Rung by another cashier." });
  });

  it("returns the invoice payload on success, as before", async () => {
    const message = { success: true, data: { name: "POS-1" } };
    vi.stubGlobal("fetch", reply(message));
    expect(await getInvoiceDetails("POS-1")).toEqual({ success: true, data: message });
  });
});
