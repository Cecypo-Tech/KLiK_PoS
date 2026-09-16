export interface StaleDraftNotice {
  message: string;
  level: "warning" | "error";
  /** True when submitting again would ring the same sale up twice. */
  blockSubmit: boolean;
}

/**
 * What to tell the cashier when the draft this sale was finishing is no longer a draft.
 *
 * A cancelled draft recorded nothing, so the link is dropped and the sale can be rung up
 * anew. A submitted one already recorded this sale - most often this dialog's own earlier
 * Submit whose reply was lost - so Submit stays blocked. Anything unrecognised is treated
 * as submitted, the side that cannot charge twice.
 */
export function staleDraftNotice(
  invoiceId: string,
  docstatus: number,
  { wasMpesaDraft = false }: { wasMpesaDraft?: boolean } = {},
): StaleDraftNotice {
  if (docstatus === 2) {
    const mpesa = wasMpesaDraft ? " The M-Pesa payment on it was cleared; take or reconcile it again." : "";
    return {
      message: `${invoiceId} was cancelled outside the POS.${mpesa} Submit again to ring this sale up as a new invoice.`,
      level: "warning",
      blockSubmit: false,
    };
  }
  return {
    message: `${invoiceId} was already submitted outside the POS, so this sale is recorded there. Submit is blocked so it is not charged twice; clear the cart to start a new sale.`,
    level: "error",
    blockSubmit: true,
  };
}
