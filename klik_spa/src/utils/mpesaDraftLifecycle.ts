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
