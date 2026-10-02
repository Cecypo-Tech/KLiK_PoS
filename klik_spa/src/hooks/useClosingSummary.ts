import { useCallback, useRef, useState } from "react";

import type { ClosingSummary } from "../utils/closingSummary";

/** The caller's shift's expected amounts per mode (klik_pos.api.pos_entry.closing_summary).
 * The page calls refresh() on load and again when the Close Shift dialog opens, so the count
 * is checked against what will be filed. Only the latest call's answer is kept. */
export function useClosingSummary() {
  const [summary, setSummary] = useState<ClosingSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const call = ++latest.current;
    setIsLoading(true);
    try {
      const response = await fetch("/api/method/klik_pos.api.pos_entry.closing_summary", { credentials: "include" });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.message) {
        const messages = JSON.parse(result._server_messages || "[]").map((m: string) => JSON.parse(m).message);
        throw new Error(messages.join(" ").replace(/<[^>]*>/g, "") || `Could not load the shift's totals (${response.status})`);
      }
      if (call !== latest.current) return;
      setSummary(result.message as ClosingSummary);
      setError(null);
    } catch (err) {
      if (call !== latest.current) return;
      setSummary(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (call === latest.current) setIsLoading(false);
    }
  }, []);

  return { summary, isLoading, error, refresh };
}
