import type { SalesInvoice } from "../../types";
import type { PaymentMode } from "../hooks/usePaymentModes";

export interface PaymentStat {
  name: string;
  openingAmount: number;
  amount: number;
  transactions: number;
}

/**
 * Expected drawer total per payment mode for the closing shift screen:
 * the till's true starting float (mode.openingAmount) plus the shift's
 * sales in that mode, summed from the invoice list.
 *
 * mode.amount is a *different* number (the backend's own sales-total for
 * the mode) and must never be read as the opening float — falling back to
 * it when openingAmount is legitimately 0 double-counts the shift's sales.
 */
export function computePaymentStats(
  modes: PaymentMode[] | undefined,
  invoices: Pick<SalesInvoice, "payment_methods" | "paymentMethod" | "totalAmount" | "status">[],
  currentShift?: string | null
): Record<string, PaymentStat> {
  const stats: Record<string, PaymentStat> = {};

  const ensurePaymentStat = (modeName?: string, openingAmount = 0) => {
    if (!modeName) return null;

    if (!stats[modeName]) {
      stats[modeName] = {
        name: modeName,
        openingAmount,
        amount: 0,
        transactions: 0,
      };
    } else if (openingAmount) {
      stats[modeName].openingAmount = openingAmount;
    }

    return stats[modeName];
  };

  (modes || []).forEach((mode) => {
    const modeName = mode.name || mode.mode_of_payment;
    const openingAmount = Number(mode.openingAmount || 0);
    ensurePaymentStat(modeName, openingAmount);
  });

  invoices.forEach((invoice) => {
    if (invoice.payment_methods && Array.isArray(invoice.payment_methods)) {
      invoice.payment_methods.forEach((payment, index) => {
        // A row read from a Payment Entry counts only when that entry was stamped with
        // the shift being closed (a receipt taken at the till). A customer advance an
        // accountant recorded carries no shift: shown on the invoice, never in the
        // cashier's hands, so not theirs to count. Same rule as the server's.
        if (payment.payment_entry && (payment.pos_opening_entry || null) !== (currentShift || null)) return;
        const stat = ensurePaymentStat(payment.mode_of_payment || undefined);
        if (!stat) return;

        const isReturn = invoice.status === "Return";
        const amount = isReturn ? -Math.abs(payment.amount || 0) : (payment.amount || 0);
        stat.amount += amount;

        if (index === 0) {
          stat.transactions += 1;
        }
      });
    } else {
      const stat = ensurePaymentStat(invoice.paymentMethod);
      if (!stat) return;

      const isReturn = invoice.status === "Return";
      const amount = isReturn ? -Math.abs(invoice.totalAmount || 0) : (invoice.totalAmount || 0);
      stat.amount += amount;
      stat.transactions += 1;
    }
  });

  // Expected drawer total = opening float + sales summed above.
  Object.values(stats).forEach((stat) => {
    stat.amount += stat.openingAmount;
  });

  return stats;
}
