import { useCallback, useEffect, useState } from "react";
import {
  buildSummaryQuery,
  isScopeComplete,
  type DashboardSummary,
  type ScopeRequest,
} from "../utils/dashboardSummary";

const ENDPOINT = "/api/method/klik_pos.api.dashboard.get_dashboard_summary";

/**
 * The whole dashboard, from one call.
 *
 * There is deliberately no partial state: either the server's balanced answer is on screen
 * or a message saying why it is not. The page this replaces rendered whatever slice of
 * invoices had arrived, which is how it came to show a total that depended on how much had
 * loaded rather than on how much had sold.
 */
export function useDashboardSummary(request: ScopeRequest) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  // The query string is the identity of the request: a new object with the same scope must
  // not refetch, and a changed scope must never leave the previous answer on screen.
  const query = buildSummaryQuery(request);
  const isComplete = isScopeComplete(request);

  useEffect(() => {
    if (!isComplete) {
      // Half-filled form, not a failure: say what is missing and ask nothing of the server.
      setSummary(null);
      setError("Pick both dates to see a custom range.");
      setIsLoading(false);
      return;
    }

    let isCurrent = true;
    const controller = new AbortController();

    setIsLoading(true);
    setError(null);

    fetch(`${ENDPOINT}?${query}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(serverMessage(body) || `Could not load the dashboard (${response.status})`);
        }
        return body?.message as DashboardSummary;
      })
      .then((data) => {
        if (!isCurrent) return;
        setSummary(data ?? null);
      })
      .catch((err: Error) => {
        if (!isCurrent || err.name === "AbortError") return;
        // A stale answer beside a fresh error reads as a working page. Clear it.
        setSummary(null);
        setError(err.message);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
      controller.abort();
    };
  }, [query, isComplete, reloadToken]);

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  return { summary, isLoading, error, refresh };
}

/** Frappe puts the readable reason in _server_messages; the raw exception is not for the till. */
function serverMessage(body: unknown): string | null {
  const payload = body as { _server_messages?: string; exception?: string } | null;
  if (!payload) return null;
  try {
    const messages = JSON.parse(payload._server_messages || "[]") as string[];
    const first = messages.length > 0 ? JSON.parse(messages[0] ?? "{}") : null;
    if (first?.message) return String(first.message).replace(/<[^>]*>/g, "");
  } catch {
    // fall through to the exception line
  }
  if (payload.exception) return payload.exception.split(":").slice(1).join(":").trim() || null;
  return null;
}
