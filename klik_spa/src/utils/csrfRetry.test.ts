import { describe, expect, it, vi } from "vitest";

import { CSRF_TOKEN_METHOD, withCsrfRetry } from "./csrfRetry";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const stale = () => json(400, { exc_type: "CSRFTokenError", _server_messages: "Invalid Request" });

describe("withCsrfRetry", () => {
  it("fetches the session's token and sends the save again once", async () => {
    const win = { csrf_token: "old" };
    const seen: (string | null)[] = [];
    const base = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes(CSRF_TOKEN_METHOD)) return json(200, { message: "fresh" });
      const token = new Headers(init?.headers).get("X-Frappe-CSRF-Token");
      seen.push(token);
      return token === "fresh" ? json(200, { message: { success: true } }) : stale();
    });

    const res = await withCsrfRetry(base, win)("/api/method/klik_pos.api.shift.join_shift", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": "old" },
      body: "{}",
    });

    expect(res.status).toBe(200);
    expect(seen).toEqual(["old", "fresh"]);
    expect(win.csrf_token).toBe("fresh");
  });

  it("leaves any other 400 alone", async () => {
    const base = vi.fn(async () => json(400, { exc_type: "ValidationError" }));
    const res = await withCsrfRetry(base, { csrf_token: "t" })("/x", {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": "t" },
    });
    expect(res.status).toBe(400);
    expect(base).toHaveBeenCalledTimes(1);
  });

  it("gives back the original failure when no fresh token comes", async () => {
    const base = vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes(CSRF_TOKEN_METHOD) ? json(403, {}) : stale(),
    );
    const res = await withCsrfRetry(base, { csrf_token: "t" })("/x", {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": "t" },
    });
    expect(res.status).toBe(400);
    expect((await res.json()).exc_type).toBe("CSRFTokenError");
  });
});
