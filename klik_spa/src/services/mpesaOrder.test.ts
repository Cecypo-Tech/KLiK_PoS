import { afterEach, describe, expect, it, vi } from "vitest";
import { discardMpesaOrder, saveMpesaOrder, submitMpesaOrder } from "./mpesaOrder";
import { HeldOrderGoneError } from "./salesOrder";

afterEach(() => vi.unstubAllGlobals());

const reply = (message: unknown) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ message }) });

const serve = (message: unknown) => {
  vi.stubGlobal("window", { csrf_token: "t" });
  const fetch = reply(message);
  vi.stubGlobal("fetch", fetch);
  return fetch;
};

describe("saveMpesaOrder", () => {
  it("sends the cart with the order it updates and returns the order's name", async () => {
    const fetch = serve({ success: true, order_name: "SAL-ORD-9", grand_total: 4 });

    await expect(saveMpesaOrder({ items: [] }, "SAL-ORD-9")).resolves.toBe("SAL-ORD-9");

    const body = JSON.parse(fetch.mock.calls[0]?.[1].body);
    expect(body.data.mpesa_order_id).toBe("SAL-ORD-9");
  });

  it("raises the server's reason when the order could not be saved", async () => {
    serve({ success: false, message: "Discount changes are not allowed" });

    await expect(saveMpesaOrder({ items: [] })).rejects.toThrow("Discount changes are not allowed");
  });
});

describe("discardMpesaOrder", () => {
  it("reports an order kept for its push, with the server's words", async () => {
    serve({ success: true, kept: true, message: "Order SAL-ORD-9 was kept" });

    await expect(discardMpesaOrder("SAL-ORD-9")).resolves.toEqual({ kept: true, message: "Order SAL-ORD-9 was kept" });
  });

  it("reports a discarded order as not kept", async () => {
    serve({ success: true, kept: false, message: "discarded" });

    await expect(discardMpesaOrder("SAL-ORD-9")).resolves.toEqual({ kept: false });
  });
});

describe("submitMpesaOrder", () => {
  it("raises a typed error naming the order that is gone", async () => {
    serve({ success: false, code: "held_order_gone", order_id: "SAL-ORD-9", message: "no longer exists" });

    const err = await submitMpesaOrder("SAL-ORD-9", {}, null, "").catch((e) => e);

    expect(err).toBeInstanceOf(HeldOrderGoneError);
    expect(err.orderId).toBe("SAL-ORD-9");
  });

  it("raises the waiting push as a plain error", async () => {
    serve({ success: false, code: "mpesa_request_waiting", error: "M-Pesa request MEXP-1 is still waiting" });

    await expect(submitMpesaOrder("SAL-ORD-9", {}, null, "")).rejects.toThrow("MEXP-1 is still waiting");
  });

  it("returns the invoice, also when the server answers a retried submit", async () => {
    const fetch = serve({ success: true, replayed: true, invoice_name: "POS-01600" });

    const result = await submitMpesaOrder("SAL-ORD-9", { items: [] }, "SAL-ORD-3", "note");

    expect(result.invoice_name).toBe("POS-01600");
    const body = JSON.parse(fetch.mock.calls[0]?.[1].body);
    expect(body).toMatchObject({ order_id: "SAL-ORD-9", held_order_id: "SAL-ORD-3", remarks: "note" });
  });
});
