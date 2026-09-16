import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchOpeningConflict, postOpeningEntry } from "./opeiningEntry";

const respond = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

afterEach(() => vi.unstubAllGlobals());

describe("postOpeningEntry", () => {
  it("reports success only when the server created the entry", async () => {
    vi.stubGlobal("fetch", respond(200, { message: { name: "POS-OPE-1" } }));
    expect(await postOpeningEntry({ opening_balance: [] }, "tok")).toEqual({ ok: true, name: "POS-OPE-1" });
  });

  it("reports a refusal as a failure with the server's words, not raw JSON", async () => {
    const msg = JSON.stringify({ message: "Your shift POS-OPE-9 on Till is already open." });
    vi.stubGlobal("fetch", respond(417, { exc_type: "ValidationError", _server_messages: JSON.stringify([msg]) }));

    const result = await postOpeningEntry({ opening_balance: [] }, "tok");

    expect(result).toEqual({ ok: false, error: "Your shift POS-OPE-9 on Till is already open." });
  });

  it("reports a network failure as a failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await postOpeningEntry({ opening_balance: [] }, "tok")).toEqual({ ok: false, error: "offline" });
  });
});

describe("fetchOpeningConflict", () => {
  it("returns the shift in the way", async () => {
    const conflict = { kind: "own_stale", entry: "POS-OPE-9", pos_profile: "Till", period_start_date: "x" };
    const fetchMock = respond(200, { message: conflict });
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchOpeningConflict("Till A")).toEqual(conflict);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("pos_profile=Till%20A");
  });

  it("returns null when nothing is in the way or the check fails", async () => {
    vi.stubGlobal("fetch", respond(200, { message: null }));
    expect(await fetchOpeningConflict("Till")).toBeNull();
    vi.stubGlobal("fetch", respond(500, {}));
    expect(await fetchOpeningConflict("Till")).toBeNull();
  });
});
