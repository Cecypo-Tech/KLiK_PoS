/**
 * The STK push's end of checkout: once the customer has paid, the sale submits itself so
 * nobody can edit or cancel a sale whose money is already in.
 *
 * Only when the paid push alone settles the server's total. Any other row holding an
 * amount (a split, or the till's default mode pre-filled with the rest) is money the
 * cashier must confirm with Submit - auto-submitting it would record cash nobody took.
 * The decision is taken once per push, after the server total is in; it never fires later
 * when some other block clears, which would submit while the cashier is still typing.
 */

export type StkAutoSubmitDecision =
  | { action: "submit" }
  | { action: "wait" }
  | { action: "notify"; reason: "other_rows" | "short" }
  | { action: "notify"; reason: "blocked"; detail: string }
  | { action: "none" };

const cents = (value: number) => Math.round(value * 100);

export function stkAutoSubmitDecision(state: {
  /** submitBlockReason(): why Submit is disabled right now, or null when it is not. */
  blockReason: string | null;
  isProcessing: boolean;
  invoiceSubmitted: boolean;
  /** The server's preview of this cart has arrived (its total is the one to settle). */
  previewReady: boolean;
  /** What the customer paid by the push. */
  paidAmount: number;
  /** What the sale asks for. */
  payable: number;
  /** Any payment row other than the paid push holds an amount. */
  otherRowsTendered: boolean;
}): StkAutoSubmitDecision {
  if (state.invoiceSubmitted || state.isProcessing) return { action: "none" };
  if (!state.previewReady) return { action: "wait" };
  if (state.otherRowsTendered) return { action: "notify", reason: "other_rows" };
  if (cents(state.paidAmount) < cents(state.payable)) return { action: "notify", reason: "short" };
  if (state.blockReason) return { action: "notify", reason: "blocked", detail: state.blockReason };
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
