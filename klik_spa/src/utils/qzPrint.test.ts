import { afterEach, describe, expect, it, vi } from "vitest";
import { qzNextStep, qzPrintCount, qzPrintOptions, qzReprint } from "./qzPrint";

vi.mock("react-toastify", () => ({ toast: { success: () => {}, warn: () => {}, error: () => {} } }));

afterEach(() => vi.unstubAllGlobals());

const serve = (reply: unknown) => {
  const fetch = vi.fn().mockImplementation(async () => reply);
  vi.stubGlobal("fetch", fetch);
  return fetch;
};

describe("qzPrintCount", () => {
  it("asks cecypo_qz_extension for the invoice's printed-job count", async () => {
    const fetch = serve({ ok: true, json: async () => ({ message: 3 }) });

    await expect(qzPrintCount("POS-01696")).resolves.toBe(3);

    const [url] = fetch.mock.calls[0] ?? [];
    expect(url).toBe(
      "/api/method/cecypo_qz_extension.api.queue.print_count?reference_doctype=Sales+Invoice&reference_name=POS-01696",
    );
  });

  it("is 0, never an error, when the server refuses", async () => {
    serve({ ok: false, json: async () => ({ exc_type: "PermissionError" }) });

    await expect(qzPrintCount("POS-01696")).resolves.toBe(0);
  });

  it("is 0 when the network is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(qzPrintCount("POS-01696")).resolves.toBe(0);
  });
});

describe("qzNextStep", () => {
  const ok = (rule: string) => ({ rule, limit_reached: false });
  const capped = (rule: string) => ({ rule, limit_reached: true });

  it("says so when no rule matches", () => {
    expect(qzNextStep([])).toEqual({ kind: "none" });
  });

  it("says so when every rule is at its limit", () => {
    expect(qzNextStep([capped("Invoice"), capped("Packing")])).toEqual({ kind: "limit" });
  });

  it("prints a single rule straight away", () => {
    expect(qzNextStep([ok("Invoice")])).toEqual({ kind: "print", rules: ["Invoice"] });
  });

  it("asks when more than one rule matches, even if some are at their limit", () => {
    const options = [ok("Invoice"), capped("Packing")];
    expect(qzNextStep(options)).toEqual({ kind: "choose", options });
  });
});

describe("a held order (Sales Order)", () => {
  it("asks for and prints the Sales Order's rules, not a Sales Invoice's", async () => {
    vi.stubGlobal("window", { csrf_token: "t" });
    const fetch = serve({ ok: true, json: async () => ({ message: [] }) });

    await qzPrintOptions("SAL-ORD-1", "Sales Order");
    await qzReprint("SAL-ORD-1", "Sales Order", ["SO - A"]);

    const bodies = fetch.mock.calls.map(([, init]) => JSON.parse(init.body));
    expect(bodies[0]).toEqual({ reference_doctype: "Sales Order", reference_name: "SAL-ORD-1" });
    expect(bodies[1]).toMatchObject({ reference_doctype: "Sales Order", rules: JSON.stringify(["SO - A"]) });
  });
});
