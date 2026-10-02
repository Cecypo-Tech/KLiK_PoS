/**
 * The draft Sales Invoice M-Pesa makes before the money moves, and when the payment dialog
 * may let go of it.
 */

export interface MpesaDraftCheckout {
  draftName: string | null;
  /** Draft creation, STK initiation, receipt reconcile or submit still running. */
  workInFlight: number;
  /** Drafts an STK push was sent (or started being sent) from in this dialog. */
  stkSentFrom: ReadonlySet<string>;
}

/**
 * The draft to discard when the cashier leaves checkout unfinished, or null to keep it.
 *
 * Kept while anything is still running against it, and for good once an STK push was sent
 * from it: the push is committed only after Safaricom accepts it, so the server cannot yet
 * see it, and a payment arriving for a deleted invoice has nowhere to land.
 */
export function mpesaDraftToDiscard({ draftName, workInFlight, stkSentFrom }: MpesaDraftCheckout): string | null {
  if (!draftName || workInFlight > 0 || stkSentFrom.has(draftName)) return null;
  return draftName;
}

/** Why the order cannot be held now, or null. */
export function holdBlockedByMpesa(
  flow: { source: "stk" | "c2b"; status: "idle" | "in_progress" | "completed" | "failed" } | null,
): string | null {
  if (flow?.source !== "stk") return null;
  if (flow.status === "in_progress") {
    return "An M-Pesa request is waiting on the customer. Wait for it to finish before holding this order.";
  }
  if (flow.status === "completed") {
    return "The customer has paid by M-Pesa. Submit the sale instead of holding it.";
  }
  return null;
}

/**
 * What to tell the cashier when the dialog keeps a draft because an STK push was sent from
 * it, or null. Kept silently, the cashier could leave, reopen checkout and charge again.
 */
export function mpesaDraftKeptForStk({ draftName, stkSentFrom }: MpesaDraftCheckout): string | null {
  if (!draftName || !stkSentFrom.has(draftName)) return null;
  return `Draft ${draftName} was kept: an M-Pesa request was sent from it, and its payment needs this invoice. Finish or cancel it from Invoice History before charging this customer again.`;
}

export type StkRetryAction =
  | { send: true; method: string; amount: number; phone: string }
  | { send: false; reason: string };

/**
 * What "Send again" does after a failed STK push: a new push for the M-Pesa amount as it
 * stands now (a discount since the failed push is respected), to the phone typed in the
 * panel or else the one the failed push went to.
 */
export function stkRetryAction(
  active: { method: string; amount: number } | null,
  phoneTyped: string,
  failedPushPhone: string | undefined,
): StkRetryAction {
  if (!active || active.amount <= 0) {
    return { send: false, reason: "Enter an amount on an M-Pesa payment method before sending the request again." };
  }
  const phone = phoneTyped.trim() || (failedPushPhone || "").trim();
  if (!phone) {
    return { send: false, reason: "Enter the customer's phone number to send the M-Pesa request again." };
  }
  return { send: true, method: active.method, amount: active.amount, phone };
}
