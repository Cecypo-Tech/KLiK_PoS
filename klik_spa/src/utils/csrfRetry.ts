export const CSRF_TOKEN_METHOD = "/api/method/klik_pos.api.user.csrf_token";

type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
/** The page's token and the user it was rendered (or last logged in) for. */
export type CsrfWindow = { csrf_token?: string; klik_user?: string };

/** The browser session's token and user, or null. */
export async function fetchSessionToken(base: Fetch): Promise<{ token: string; user: string } | null> {
  return base(CSRF_TOKEN_METHOD, { credentials: "include", headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => (d?.message?.token ? (d.message as { token: string; user: string }) : null))
    .catch(() => null);
}

/**
 * The till keeps the CSRF token its page was rendered with. Log in again - its own login
 * screen, or desk in another tab - and the session holds a new one, so every save fails
 * Frappe's 400 "Invalid Request" until a reload. On that failure, ask the session for its
 * token and send the request once more - but only while the session is still the till's
 * user: someone else logged in since would otherwise write under the cashier's screen.
 */
export function withCsrfRetry(base: Fetch, win: CsrfWindow): Fetch {
  return async (input, init) => {
    const res = await base(input, init);
    const headers = new Headers(init?.headers);
    if (res.status !== 400 || !headers.has("X-Frappe-CSRF-Token")) return res;
    const body = await res.clone().json().catch(() => null);
    if (body?.exc_type !== "CSRFTokenError") return res;

    const session = await fetchSessionToken(base);
    if (!session) return res;
    if (session.user !== win.klik_user) {
      const message = `This browser is now logged in as ${session.user}. Reload the page to continue.`;
      return new Response(
        JSON.stringify({ exc_type: "CSRFTokenError", _server_messages: JSON.stringify([JSON.stringify({ message })]) }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    win.csrf_token = session.token;
    headers.set("X-Frappe-CSRF-Token", session.token);
    return base(input, { ...init, headers });
  };
}
