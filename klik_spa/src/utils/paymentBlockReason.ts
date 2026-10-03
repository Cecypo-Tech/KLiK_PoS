export interface PaymentBlockState {
  invoiceSubmitted: boolean;
  isProcessingPayment: boolean;
  reconciliationOk: boolean;
  reconciliationMessage: string | null;
  isCreditSale: boolean;
  hasDueDate: boolean;
  /** The customer's payment terms are still loading: the due date shown is not theirs yet. */
  creditTermsLoading?: boolean;
  isB2C: boolean;
  outstandingAmount: number;
  /** outstandingAmount formatted in the sale's currency. */
  outstandingLabel: string;
  /** Set when this sale is already recorded as that invoice (submitted outside the POS). */
  alreadySubmittedAs: string | null;
  /** Why a held order this cart came from still cannot be checked out, or null. */
  priceApprovalMessage: string | null;
  /** The M-Pesa amount no picked receipt or completed STK push covers, formatted, or null. */
  mpesaUncoveredLabel: string | null;
  /** With vouchers applied, an overpay no cash row can hand back as change, formatted, or null. */
  overpaidNonCashLabel?: string | null;
}

/**
 * Why the payment dialog's Submit is disabled, or null when it is not. The button and
 * the F10 shortcut share this, so a shortcut that cannot submit can say why.
 */
export function paymentBlockReason(s: PaymentBlockState): string | null {
  if (s.invoiceSubmitted) return "This invoice is already submitted";
  if (s.alreadySubmittedAs) {
    return `This sale is already recorded as ${s.alreadySubmittedAs}; clear the cart to start a new sale`;
  }
  if (s.priceApprovalMessage) return s.priceApprovalMessage;
  if (s.isProcessingPayment) return "Payment is already being processed";
  if (s.mpesaUncoveredLabel) return `Pick the M-Pesa receipt or send an STK push for ${s.mpesaUncoveredLabel}`;
  if (!s.reconciliationOk) return s.reconciliationMessage || "This sale is on hold";
  if (s.isCreditSale && !s.hasDueDate) return "Select a due date for this credit sale";
  if (s.isCreditSale && s.creditTermsLoading) return "Loading the customer's payment terms";
  if (s.overpaidNonCashLabel) return `Overpaid by ${s.overpaidNonCashLabel} on a non-cash method - reduce it`;
  if (s.isB2C && !s.isCreditSale && s.outstandingAmount > 0) {
    return `${s.outstandingLabel} still to be paid`;
  }
  return null;
}
