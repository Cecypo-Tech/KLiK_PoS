import {  useState} from "react";
import type { OpeningSuggestion } from "../utils/openingBalances";

/**
 * What this till last closed at, per mode. Drives the opening screen's suggested figures;
 * the same rules are enforced again server-side when the entry is created.
 */
export async function fetchOpeningSuggestion(posProfile: string): Promise<OpeningSuggestion | null> {
  if (!posProfile) return null;
  try {
    const res = await fetch(
      `/api/method/klik_pos.api.opening_balances.opening_suggestion?pos_profile=${encodeURIComponent(posProfile)}`,
      { credentials: "include", headers: { Accept: "application/json" } },
    );
    if (!res.ok) return null;
    const data = await res.json();
    return (data?.message as OpeningSuggestion) ?? null;
  } catch (err) {
    // A missing suggestion is not a reason to block opening a till: every rule it feeds
    // is checked again on the server when the entry is saved.
    console.warn("Could not load opening suggestions:", err);
    return null;
  }
}

// HOOK 2: Create POS Opening Entry
interface OpeningBalance {
  mode_of_payment: string;
  opening_amount: number;
  /** Why this differs from what the till last closed at. Required by the server when it does. */
  variance_reason?: string;
}

interface UseCreateOpeningReturn {
  createOpeningEntry: (openingBalance: OpeningBalance[], posProfile?: string) => Promise<void>;
  isCreating: boolean;
  error: string | null;
  success: boolean;
}

export function useCreatePOSOpeningEntry(): UseCreateOpeningReturn {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const createOpeningEntry = async (openingBalance: OpeningBalance[], posProfile?: string) => {
    setIsCreating(true);
    setError(null);
    setSuccess(false);
    const csrfToken = window.csrf_token;

    try {
      //eslint-disable-next-line @typescript-eslint/no-explicit-any
      const requestBody: any = { opening_balance: openingBalance };
      if (posProfile) {
        requestBody.pos_profile = posProfile;
      }

      const res = await fetch("/api/method/klik_pos.api.pos_entry.create_opening_entry", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          'X-Frappe-CSRF-Token': csrfToken
        },
        body: JSON.stringify(requestBody),
        credentials: "include"
      });

      const data = await res.json();

      if (res.ok && data.message) {
        setSuccess(true);
      } else {
        throw new Error(data._server_messages || "Failed to create opening entry");
      }
            //eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      console.error("Error creating POS Opening Entry:", err);
      setError(err.message || "Unexpected error occurred");
    } finally {
      setIsCreating(false);
    }
  };

  return {
    createOpeningEntry,
    isCreating,
    error,
    success,
  };
}
