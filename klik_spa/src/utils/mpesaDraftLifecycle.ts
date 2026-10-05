/** The M-Pesa order a push is sent from, and when the payment dialog may let go of it. */

/** Why the order cannot be held now, or null. */
export function holdBlockedByMpesa(
  flow: {
    source: "stk" | "c2b";
    status: "idle" | "in_progress" | "completed" | "failed";
    transactionId?: string;
  } | null,
): string | null {
  if (flow?.source !== "stk") return null;
  if (flow.status === "in_progress") {
    return "An M-Pesa request is waiting on the customer. Wait for it to finish before holding this order.";
  }
  if (flow.status === "completed" && !flow.transactionId) {
    // Paid with its receipt pending (utils/stkPushCheck): the order is on the Held tab already.
    return "The customer has paid, but the M-Pesa receipt has not arrived. Close checkout: the sale stays on Held with its payment.";
  }
  if (flow.status === "completed") {
    return "The customer has paid by M-Pesa. Submit the sale instead of holding it.";
  }
  return null;
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

/** An Mpesa Express Request status, as the payment dialog tracks it. */
export function normalizeMpesaStatus(status?: string) {
  const normalized = (status || "").toLowerCase();
  if (["completed", "success", "successful"].includes(normalized)) return "completed" as const;
  if (["failed", "cancelled", "timed out", "timeout"].includes(normalized)) return "failed" as const;
  if (normalized === "idle") return "idle" as const;
  return "in_progress" as const;
}

/**
 * The M-Pesa order to hand back to the server when the cashier leaves checkout, or null.
 *
 * The server deletes it, or keeps it as a held order when a push from it may still pay. It
 * cannot judge while a push is still being sent - that push is committed only once Safaricom
 * accepts it - so the order is left alone then, for the shift close to settle.
 */
export function mpesaOrderToRelease(orderName: string | null, workInFlight: number): string | null {
  if (!orderName || workInFlight > 0) return null;
  return orderName;
}

/** The newest push of a kept M-Pesa order, as the held order's details carry it. */
export interface KeptMpesaPush {
  name: string;
  status: string;
  amount?: number;
  phone_number?: string;
  transaction_id?: string | null;
  checkout_request_id?: string | null;
  payment_gateway?: string | null;
  result_desc?: string | null;
}

/**
 * Checkout resumed from a kept M-Pesa order picks up its push - a paid one is submitted, not
 * charged again - on the mode it went through, or else the till's first M-Pesa mode.
 */
export function resumedMpesaFlow(orderId: string, push: KeptMpesaPush | null, mpesaModes: string[]) {
  if (!push) return null;
  const modeOfPayment =
    push.payment_gateway && mpesaModes.includes(push.payment_gateway) ? push.payment_gateway : mpesaModes[0];
  if (!modeOfPayment) return null;
  return {
    modeOfPayment,
    amount: Number(push.amount || 0),
    phoneNumber: push.phone_number || "",
    accountReference: orderId,
    source: "stk" as const,
    requestName: push.name,
    transactionId: push.transaction_id || undefined,
    checkoutRequestId: push.checkout_request_id || undefined,
    status: normalizeMpesaStatus(push.status),
    message: push.result_desc || undefined,
  };
}
