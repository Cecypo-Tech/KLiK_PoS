export interface StaleDraftNotice {
  message: string;
  level: "warning" | "error";
}

/**
 * What to tell the cashier when the draft this sale was finishing is no longer a draft.
 * The link to it has been dropped either way; the difference is whether submitting again
 * is safe. A cancelled draft recorded nothing, so the sale can be rung up anew. A submitted
 * one already recorded this sale, and ringing it up again would charge it twice.
 */
export function staleDraftNotice(invoiceId: string, docstatus: number): StaleDraftNotice {
  if (docstatus === 2) {
    return {
      message: `${invoiceId} was cancelled outside the POS. Submit again to ring this sale up as a new invoice.`,
      level: "warning",
    };
  }
  return {
    message: `${invoiceId} was already submitted outside the POS. Check it before submitting again, or this sale will be charged twice.`,
    level: "error",
  };
}
