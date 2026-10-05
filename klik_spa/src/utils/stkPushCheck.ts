/**
 * An STK push whose confirmation has not arrived (klik_pos.api.mpesa_order). Safaricom's success
 * callback is sometimes lost, so the till asks Safaricom itself: 20 s into the wait, then every
 * 15 s while it waits. Safaricom's "paid" answer has no receipt number; the sale submits on it,
 * and the receipt number follows when the receipt reaches the register (frappe_mpsa_payments
 * matches it to the push by the order number).
 */

export const AUTO_CHECK_FIRST_MS = 20_000;
export const AUTO_CHECK_EVERY_MS = 15_000;

interface StkFlow {
  source: "stk" | "c2b";
  status: "idle" | "in_progress" | "completed" | "failed";
  requestName?: string;
}

/** When the till next asks Safaricom about the waiting push, or null: the first ask for a push
 * not yet asked about (`checkedFor` is the push last asked about), then every 15 s. */
export function autoCheckDelay(flow: StkFlow | null, checkedFor: string | null): number | null {
  if (flow?.source !== "stk" || flow.status !== "in_progress" || !flow.requestName) return null;
  return flow.requestName === checkedFor ? AUTO_CHECK_EVERY_MS : AUTO_CHECK_FIRST_MS;
}

/** check_mpesa_push's answer. */
export type PushCheck =
  | { outcome: "paid"; transaction_id?: string | null }
  | { outcome: "not_paid"; reason?: string | null }
  | { outcome: "waiting" }
  | { outcome: "no_answer" };

/** What the till says after asking Safaricom. */
export function pushCheckMessage(check: PushCheck): string {
  switch (check.outcome) {
    case "paid":
      return "Payment confirmed";
    case "not_paid":
      return check.reason || "Not paid";
    case "waiting":
      return "The customer is still being asked - check again shortly.";
    case "no_answer":
      return "Couldn't get an answer from Safaricom - try again.";
  }
}
