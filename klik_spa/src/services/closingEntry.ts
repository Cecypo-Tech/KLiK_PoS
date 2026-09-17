import { useState } from "react";
import { extractErrorMessage } from "../utils/errorExtraction";

// HOOK: Create POS Closing Entry
interface ClosingBalance {
  mode_of_payment: string;
  closing_amount: number;
}

export type ClosingResult = { ok: true } | { ok: false; error: string };

/** Posts the shift close, and reports a refusal in the server's own words - a manager-only
 * rule, in particular, must not be mistaken for success. */
export async function postClosingEntry(
  closingBalance: ClosingBalance[],
  csrfToken: string,
): Promise<ClosingResult> {
  try {
    const res = await fetch("/api/method/klik_pos.api.pos_entry.create_closing_entry", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrfToken,
        "Accept": "application/json",
      },
      body: JSON.stringify({ closing_balance: closingBalance }),
      credentials: "include",
    });
    // A proxy error page is HTML, not JSON; it still has to read as a failure.
    const data = await res.json().catch(() => null);
    if (res.ok && data?.message) {
      return { ok: true };
    }
    return { ok: false, error: extractErrorMessage(data, "Failed to close the shift") };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unexpected error occurred" };
  }
}

interface UseCreateClosingReturn {
  createClosingEntry: (closingBalance: ClosingBalance[]) => Promise<ClosingResult>;
  isCreating: boolean;
  error: string | null;
  success: boolean;
}

export function useCreatePOSClosingEntry(): UseCreateClosingReturn {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const createClosingEntry = async (closingBalance: ClosingBalance[]) => {
    setIsCreating(true);
    setError(null);
    setSuccess(false);

    const result = await postClosingEntry(closingBalance, window.csrf_token);
    if (result.ok) {
      setSuccess(true);
    } else {
      console.error("Error creating POS Closing Entry:", result.error);
      setError(result.error);
    }
    setIsCreating(false);
    return result;
  };

  return {
    createClosingEntry,
    isCreating,
    error,
    success,
  };
}
