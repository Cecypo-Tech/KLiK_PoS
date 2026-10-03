/**
 * The STK push's end of checkout: once the customer has paid, the sale submits itself so
 * nobody can edit or cancel a sale whose money is already in.
 *
 * The decision is taken once, at the moment the payment is confirmed. It never fires again
 * later when some other block clears: auto-submitting while the cashier is still typing a
 * cash amount would ring up a figure they had not finished entering.
 */

export type StkAutoSubmitDecision =
  | { action: "submit" }
  | { action: "notify"; reason: string }
  | { action: "none" };

export function stkAutoSubmitDecision(state: {
  /** submitBlockReason(): why Submit is disabled right now, or null when it is not. */
  blockReason: string | null;
  isProcessing: boolean;
  invoiceSubmitted: boolean;
}): StkAutoSubmitDecision {
  if (state.invoiceSubmitted || state.isProcessing) return { action: "none" };
  if (state.blockReason) return { action: "notify", reason: state.blockReason };
  return { action: "submit" };
}

/** Send STK Push - the button and Enter in the phone box share this rule. */
export function canSendStk(state: { isProcessing: boolean; stkPending: boolean; stkPaid: boolean }): boolean {
  return !state.isProcessing && !state.stkPending && !state.stkPaid;
}

/**
 * The methods auto-allocation may reset and refill after `methodId` changes: every later
 * method, except a row holding a paid STK push - that amount is money already received.
 */
export function nextAllocationTargets(
  orderedMethodIds: string[],
  methodId: string,
  lockedMethodId: string | null,
): string[] {
  const index = orderedMethodIds.indexOf(methodId);
  if (index === -1) return [];
  return orderedMethodIds.slice(index + 1).filter((id) => id !== lockedMethodId);
}
