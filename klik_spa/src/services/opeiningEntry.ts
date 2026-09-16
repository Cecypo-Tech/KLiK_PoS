import {  useState} from "react";
import type { OpeningSuggestion } from "../utils/openingBalances";
import type { OpeningConflict } from "../utils/openingConflict";
import { extractErrorMessage } from "../utils/errorExtraction";

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

/** The cashier's own open shift in the way of opening `posProfile`, or null. */
export async function fetchOpeningConflict(posProfile: string): Promise<OpeningConflict | null> {
  if (!posProfile) return null;
  try {
    const res = await fetch(
      `/api/method/klik_pos.api.pos_entry.opening_conflict?pos_profile=${encodeURIComponent(posProfile)}`,
      { credentials: "include", headers: { Accept: "application/json" } },
    );
    if (!res.ok) return null;
    const data = await res.json();
    return (data?.message as OpeningConflict) ?? null;
  } catch (err) {
    // Create checks again, so a failed pre-check only costs the early warning.
    console.warn("Could not check for an open shift:", err);
    return null;
  }
}

export interface CurrentShiftState {
  entry: string | null;
  stale: boolean;
  pos_profile: string | null;
}

/**
 * The caller's current shift (their own, or the till shift they joined), and whether it
 * was opened on an earlier day. `open_pos` alone can't tell a stale own shift from a fresh
 * one - both read as "has an open entry" - so the guard needs this to route a stale shift
 * to Closing Shift instead of letting the cashier sell against it.
 */
export async function fetchCurrentShiftState(): Promise<CurrentShiftState | null> {
  try {
    const res = await fetch("/api/method/klik_pos.api.pos_entry.current_shift_state", {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return (data?.message as CurrentShiftState) ?? null;
  } catch (err) {
    // A failed check is not a reason to block the guard's normal flow; it just skips
    // the stale-shift redirect for this pass.
    console.warn("Could not check current shift state:", err);
    return null;
  }
}

/** Joins the shift already open on `posProfile`, so a second cashier can sell on that till. */
export async function joinShift(posProfile: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await fetch("/api/method/klik_pos.api.shift.join_shift", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.csrf_token },
      body: JSON.stringify({ pos_profile: posProfile }),
      credentials: "include",
    });
    const data = await res.json().catch(() => null);
    if (res.ok && data?.message?.success) return { ok: true };
    return { ok: false, error: extractErrorMessage(data, "Could not join the shift") };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not join the shift" };
  }
}

export type OpeningResult = { ok: true; name: string } | { ok: false; error: string };

export async function postOpeningEntry(body: object, csrfToken: string): Promise<OpeningResult> {
  try {
    const res = await fetch("/api/method/klik_pos.api.pos_entry.create_opening_entry", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
      credentials: "include",
    });
    // A proxy error page is HTML, not JSON; it still has to read as a failure.
    const data = await res.json().catch(() => null);
    if (res.ok && data?.message?.name) {
      return { ok: true, name: data.message.name };
    }
    return { ok: false, error: extractErrorMessage(data, "Failed to create opening entry") };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unexpected error occurred" };
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
  createOpeningEntry: (openingBalance: OpeningBalance[], posProfile?: string) => Promise<OpeningResult>;
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

    const requestBody: { opening_balance: OpeningBalance[]; pos_profile?: string } = {
      opening_balance: openingBalance,
    };
    if (posProfile) {
      requestBody.pos_profile = posProfile;
    }

    const result = await postOpeningEntry(requestBody, window.csrf_token);
    if (result.ok) {
      setSuccess(true);
    } else {
      console.error("Error creating POS Opening Entry:", result.error);
      setError(result.error);
    }
    setIsCreating(false);
    return result;
  };

  return {
    createOpeningEntry,
    isCreating,
    error,
    success,
  };
}
