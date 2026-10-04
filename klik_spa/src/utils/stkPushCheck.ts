/**
 * An STK push whose confirmation never arrived (klik_pos.api.mpesa_order). A minute into the
 * wait the till asks Safaricom once by itself, then offers "Check with M-Pesa". Safaricom's
 * "paid" answer has no receipt number: the push is then paid with its receipt pending - it
 * cannot be submitted - until the cashier attaches its receipt from the register, or leaves the
 * sale on Held to finish later.
 */

export const AUTO_CHECK_AFTER_MS = 60_000;
export const RECEIPT_POLL_MS = 5_000;
/** The receipt lookup asks for a pull at once, then again 30 s and 90 s in. */
const PULL_AT_MS = [0, 30_000, 90_000];
const GIVE_UP_AFTER_MS = 120_000;

export const RECEIPT_PENDING_MESSAGE = "Safaricom says paid - finding the receipt...";
export const RECEIPT_GIVE_UP_MESSAGE =
  "Safaricom confirmed the payment, but its receipt hasn't arrived yet. Keep the sale on Held and finish it from the Held tab later.";

interface StkFlow {
  source: "stk" | "c2b";
  status: "idle" | "in_progress" | "completed" | "failed";
  requestName?: string;
  transactionId?: string;
}

/** Safaricom said paid, but the push has no receipt number yet: it cannot be submitted. */
export function stkReceiptPending(flow: StkFlow | null): boolean {
  return flow?.source === "stk" && flow.status === "completed" && !flow.transactionId;
}

/** The push the till checks by itself a minute into the wait - each push once, only while it waits - or null. */
export function autoCheckFor(flow: StkFlow | null, checkedFor: string | null): string | null {
  if (flow?.source !== "stk" || flow.status !== "in_progress" || !flow.requestName) return null;
  return flow.requestName === checkedFor ? null : flow.requestName;
}

/** What the receipt lookup does on a poll `elapsedMs` after it began, having asked for `pulls` pulls. */
export function receiptLookupStep(elapsedMs: number, pulls: number): { pull: boolean; giveUp: boolean } {
  const nextPull = PULL_AT_MS[pulls];
  return { pull: nextPull !== undefined && elapsedMs >= nextPull, giveUp: elapsedMs >= GIVE_UP_AFTER_MS };
}

/** The receipt ticked for the cashier: the only match, never one of several. */
export function pretickedReceipt<T>(matches: T[]): T | null {
  return matches.length === 1 ? (matches[0] ?? null) : null;
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
      return check.transaction_id ? "Payment confirmed" : RECEIPT_PENDING_MESSAGE;
    case "not_paid":
      return check.reason || "Not paid";
    case "waiting":
      return "The customer is still being asked - check again shortly.";
    case "no_answer":
      return "Couldn't get an answer from Safaricom - try again.";
  }
}
