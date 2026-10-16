import { describe, expect, it, vi } from "vitest";

import { CSRF_TOKEN_METHOD, withCsrfRetry } from "./csrfRetry";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const stale = () => json(400, { exc_type: "CSRFTokenError", _server_messages: "Invalid Request" });
const post = (token: string) => ({
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": token },
  body: "{}",
});

function server(sessionUser: string) {
  const seen: (string | null)[] = [];
  const base = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes(CSRF_TOKEN_METHOD)) return json(200, { message: { token: "fresh", user: sessionUser } });
    const token = new Headers(init?.headers).get("X-Frappe-CSRF-Token");
    seen.push(token);
    return token === "fresh" ? json(200, { message: { success: true } }) : stale();
  });
  return { base, seen };
}

describe("withCsrfRetry", () => {
  it("fetches the session's token and sends the save again once", async () => {
    const win = { csrf_token: "old", klik_user: "a@x.com" };
    const { base, seen } = server("a@x.com");

    const res = await withCsrfRetry(base, win)("/api/method/klik_pos.api.shift.join_shift", post("old"));

    expect(res.status).toBe(200);
    expect(seen).toEqual(["old", "fresh"]);
    expect(win.csrf_token).toBe("fresh");
  });

  it("does not save as someone else who logged in since", async () => {
    // A manager logging into desk in another tab swaps the browser's session; the till
    // still shows the cashier, so writing as the manager would be a silent impersonation.
    const win = { csrf_token: "old", klik_user: "cashier@x.com" };
    const { base, seen } = server("manager@x.com");

    const res = await withCsrfRetry(base, win)("/x", post("old"));

    expect(res.status).toBe(400);
    expect(seen).toEqual(["old"]);
    expect(win.csrf_token).toBe("old");
    expect(JSON.stringify(await res.json())).toMatch(/manager@x\.com.*Reload/);
  });

  it("leaves any other 400 alone", async () => {
    const base = vi.fn(async () => json(400, { exc_type: "ValidationError" }));
    const res = await withCsrfRetry(base, { csrf_token: "t", klik_user: "a" })("/x", post("t"));
    expect(res.status).toBe(400);
    expect(base).toHaveBeenCalledTimes(1);
  });

  it("gives back the original failure when no fresh token comes", async () => {
    const base = vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes(CSRF_TOKEN_METHOD) ? json(403, {}) : stale(),
    );
    const res = await withCsrfRetry(base, { csrf_token: "t", klik_user: "a" })("/x", post("t"));
    expect(res.status).toBe(400);
    expect((await res.json()).exc_type).toBe("CSRFTokenError");
  });
});
