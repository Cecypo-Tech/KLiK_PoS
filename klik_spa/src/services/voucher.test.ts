import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCustomerRecord, lookupCreditVoucher } from "./voucher";

afterEach(() => vi.unstubAllGlobals());

type Reply = { ok: boolean; status: number; json: () => Promise<unknown> };

const answer = (message: unknown): Reply => ({ ok: true, status: 200, json: async () => ({ message }) });

const serve = (reply: Reply) => {
  vi.stubGlobal("window", { csrf_token: "t" });
  const fetch = vi.fn().mockResolvedValue(reply);
  vi.stubGlobal("fetch", fetch);
  return fetch;
};

describe("lookupCreditVoucher", () => {
  it("posts both numbers in the body with the CSRF token and returns what the server found", async () => {
    const found = { status: "open", note: "X-POS-00025", original: "POS-01696", available: 500, total: 500 };
    const fetch = serve(answer(found));

    await expect(lookupCreditVoucher("X-POS-00025", "POS-01696")).resolves.toEqual(found);

    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(url).toBe("/api/method/klik_pos.api.customer_credit.lookup_credit_voucher");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "X-Frappe-CSRF-Token": "t" });
    expect(JSON.parse(init.body)).toEqual({ credit_note: "X-POS-00025", original_invoice: "POS-01696" });
  });

  it("asks the cashier to wait when the checks are rate-limited", async () => {
    serve({ ok: false, status: 429, json: async () => ({}) });

    await expect(lookupCreditVoucher("X-POS-00025", "POS-01696")).rejects.toThrow(
      "Too many voucher checks - wait a minute and try again.",
    );
  });

  it("names the server's status when the check fails", async () => {
    serve({ ok: false, status: 500, json: async () => ({ exc_type: "AttributeError" }) });

    await expect(lookupCreditVoucher("X-POS-00025", "POS-01696")).rejects.toThrow(
      "Could not check the voucher (server answered 500)",
    );
  });

  it("treats a reply that is not JSON as a failed check", async () => {
    serve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError("Unexpected token '<'")) });

    await expect(lookupCreditVoucher("X-POS-00025", "POS-01696")).rejects.toThrow(
      "Could not check the voucher (server answered 200)",
    );
  });
});

describe("fetchCustomerRecord", () => {
  it("is null when the server cannot load the customer", async () => {
    serve(answer({ success: false }));

    await expect(fetchCustomerRecord("CRN TEST")).resolves.toBeNull();
  });

  it("is null when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(fetchCustomerRecord("CRN TEST")).resolves.toBeNull();
  });

  it("returns the customer as the till holds one", async () => {
    serve(answer({ name: "CRN TEST", customer_name: "CRN Test Ltd", customer_type: "Individual" }));

    const customer = await fetchCustomerRecord("CRN TEST");

    expect(customer?.customerName).toBe("CRN Test Ltd");
  });
});
