export const CSRF_TOKEN_METHOD = "/api/method/klik_pos.api.user.csrf_token";

type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

/**
 * The till keeps the CSRF token its page was rendered with. Log in again - its own login
 * screen, or desk in another tab - and the session holds a new one, so every save fails
 * Frappe's 400 "Invalid Request" until a reload. On that failure, ask the session for its
 * token and send the request once more.
 */
export function withCsrfRetry(base: Fetch, win: { csrf_token?: string }): Fetch {
  return async (input, init) => {
    const res = await base(input, init);
    const headers = new Headers(init?.headers);
    if (res.status !== 400 || !headers.has("X-Frappe-CSRF-Token")) return res;
    const body = await res.clone().json().catch(() => null);
    if (body?.exc_type !== "CSRFTokenError") return res;

    const fresh = await base(CSRF_TOKEN_METHOD, { credentials: "include", headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.message as string | undefined)
      .catch(() => undefined);
    if (!fresh) return res;

    win.csrf_token = fresh;
    headers.set("X-Frappe-CSRF-Token", fresh);
    return base(input, { ...init, headers });
  };
}
