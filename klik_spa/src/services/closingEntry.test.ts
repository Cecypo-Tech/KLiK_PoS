import { afterEach, describe, expect, it, vi } from "vitest";
import { postClosingEntry } from "./closingEntry";

const respond = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

afterEach(() => vi.unstubAllGlobals());

describe("postClosingEntry", () => {
  it("reports success when the server closes the shift", async () => {
    vi.stubGlobal("fetch", respond(200, { message: { name: "POS-CLO-1" } }));
    expect(await postClosingEntry([], "tok")).toEqual({ ok: true });
  });

  it("reports a manager-only refusal in the server's words", async () => {
    const msg = JSON.stringify({ message: "Only a manager can close POS-OPE-9, opened on 2026-09-16 by A." });
    vi.stubGlobal("fetch", respond(403, { exc_type: "PermissionError", _server_messages: JSON.stringify([msg]) }));

    const result = await postClosingEntry([], "tok");

    expect(result).toEqual({
      ok: false,
      error: "Only a manager can close POS-OPE-9, opened on 2026-09-16 by A.",
    });
  });

  it("reports a proxy error page, which is not JSON, as a failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new SyntaxError("Unexpected token <"); } }),
    );
    expect(await postClosingEntry([], "tok")).toEqual({
      ok: false,
      error: "Failed to close the shift",
    });
  });

  it("reports a network failure as a failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await postClosingEntry([], "tok")).toEqual({ ok: false, error: "offline" });
  });
});
