import { useCallback, useState } from "react";

import type { ClosingSummary } from "../utils/closingSummary";

/** The caller's shift's expected amounts per mode (klik_pos.api.pos_entry.closing_summary).
 * The page calls refresh() - on load and whenever its invoice list changes (a return or an
 * edit made from it). */
export function useClosingSummary() {
  const [summary, setSummary] = useState<ClosingSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch("/api/method/klik_pos.api.pos_entry.closing_summary", { credentials: "include" });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.message) {
        const messages = JSON.parse(result._server_messages || "[]").map((m: string) => JSON.parse(m).message);
        throw new Error(messages.join(" ").replace(/<[^>]*>/g, "") || `Could not load the shift's totals (${response.status})`);
      }
      setSummary(result.message as ClosingSummary);
      setError(null);
    } catch (err) {
      setSummary(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { summary, isLoading, error, refresh };
}
