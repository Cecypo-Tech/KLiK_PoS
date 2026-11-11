import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CHECKOUT_LOST_CONTACT, createSalesInvoice } from "./salesInvoice";

const reply = (body: string, status = 200) => vi.fn(async () => new Response(body, { status }));

describe("createSalesInvoice when the server's reply is lost", () => {
  beforeEach(() => vi.stubGlobal("window", { csrf_token: "t" }));
  afterEach(() => vi.unstubAllGlobals());

  it("a cut-off or HTML reply says contact was lost, not a JSON parse error, and claims no reply", async () => {
    vi.stubGlobal("fetch", reply("<html>502 Bad Gateway</html>", 502));
    const err = await createSalesInvoice({}).catch((e) => e);
    expect(err.message).toBe(CHECKOUT_LOST_CONTACT);
    // No reply: the payment dialog keeps the checkout id, so a retry replays instead of selling twice.
    expect(err.checkoutResponseReceived).toBeUndefined();
  });

  it("a dropped connection says the same", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await createSalesInvoice({}).catch((e) => e);
    expect(err.message).toBe(CHECKOUT_LOST_CONTACT);
    expect(err.checkoutResponseReceived).toBeUndefined();
  });

  it("a server error with a JSON reply still carries the server's message", async () => {
    vi.stubGlobal("fetch", reply(JSON.stringify({ message: { success: false, error: "Out of stock" } }), 200));
    const err = await createSalesInvoice({}).catch((e) => e);
    expect(err.message).not.toBe(CHECKOUT_LOST_CONTACT);
    expect(err.checkoutResponseReceived).toBe(true);
  });
});
