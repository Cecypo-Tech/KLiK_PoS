import { extractErrorMessage } from "../utils/errorExtraction";

const API = "/api/method/klik_pos.api.expense.";

export interface ShiftExpense {
  name: string;
  label: string;
  note: string;
  amount: number;
  owner: string;
  /** 0 = draft awaiting approval, 1 = submitted. */
  docstatus: number;
  creation: string;
}

export type RecordExpenseResult = { ok: true; name: string; docstatus: number } | { ok: false; error: string };

async function get<T>(method: string): Promise<T[]> {
  try {
    const res = await fetch(API + method, { credentials: "include", headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => null);
    return res.ok && Array.isArray(data?.message) ? data.message : [];
  } catch {
    return [];
  }
}

export const getExpenseTypes = () => get<{ label: string }>("expense_types");
export const getShiftExpenses = () => get<ShiftExpense>("shift_expenses");

/** Records the expense; a refusal comes back in the server's own words. */
export async function recordExpense(
  label: string,
  amount: number,
  note: string,
  csrfToken: string,
): Promise<RecordExpenseResult> {
  try {
    const res = await fetch(API + "record_expense", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrfToken, Accept: "application/json" },
      body: JSON.stringify({ label, amount, note }),
      credentials: "include",
    });
    const data = await res.json().catch(() => null);
    if (res.ok && data?.message) {
      return { ok: true, name: data.message.name, docstatus: data.message.docstatus };
    }
    return { ok: false, error: extractErrorMessage(data, "Failed to save the expense") };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unexpected error occurred" };
  }
}
