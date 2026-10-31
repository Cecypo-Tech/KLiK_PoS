import { afterEach, describe, expect, it, vi } from "vitest";
import { getExpenseTypes, getShiftExpenses, recordExpense } from "./expense";

const respond = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

afterEach(() => vi.unstubAllGlobals());

describe("recordExpense", () => {
  it("POSTs label, amount and note with the CSRF header", async () => {
    const fetchMock = respond(200, { message: { name: "ACC-JV-1", docstatus: 1 } });
    vi.stubGlobal("fetch", fetchMock);

    const result = await recordExpense("Fuel", 12.5, "van", "tok");

    expect(result).toEqual({ ok: true, name: "ACC-JV-1", docstatus: 1 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/method/klik_pos.api.expense.record_expense");
    expect(init.method).toBe("POST");
    expect(init.headers["X-Frappe-CSRF-Token"]).toBe("tok");
    expect(JSON.parse(init.body)).toEqual({ label: "Fuel", amount: 12.5, note: "van" });
  });

  it("reports a server refusal in the server's words", async () => {
    const msg = JSON.stringify({ message: "Open a shift first." });
    vi.stubGlobal("fetch", respond(417, { exc_type: "ValidationError", _server_messages: JSON.stringify([msg]) }));
    expect(await recordExpense("Fuel", 5, "", "tok")).toEqual({ ok: false, error: "Open a shift first." });
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await recordExpense("Fuel", 5, "", "tok")).toEqual({ ok: false, error: "offline" });
  });
});

describe("getters", () => {
  it("returns the types and the shift's expenses", async () => {
    vi.stubGlobal("fetch", respond(200, { message: [{ label: "Fuel" }] }));
    expect(await getExpenseTypes()).toEqual([{ label: "Fuel" }]);
    vi.stubGlobal("fetch", respond(200, { message: [{ name: "J1" }] }));
    expect(await getShiftExpenses()).toEqual([{ name: "J1" }]);
  });

  it("returns an empty list on failure", async () => {
    vi.stubGlobal("fetch", respond(403, {}));
    expect(await getExpenseTypes()).toEqual([]);
    expect(await getShiftExpenses()).toEqual([]);
  });
});
