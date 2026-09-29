import type { MpesaRegisterPayment } from "../services/mpesa";
import { roundCurrency } from "./currencyMath";

export interface ReceiptCardState {
  kind: "new" | "open" | "other";
  openAmount: number;
  total: number;
  usedCount: number;
  heldBy: string | null;
  selectable: boolean;
}

/**
 * How the picker shows one receipt: untouched (its full amount), part-used by this sale's
 * customer (what is left), or held by someone else (listed, not pickable - a leftover can
 * pay only the customer its Payment Entry belongs to).
 */
export function receiptCardState(p: MpesaRegisterPayment): ReceiptCardState {
  const total = Number(p.transamount || 0);
  const openAmount = Number(p.open_amount ?? total);
  const selectable = p.selectable ?? true;
  const kind = !selectable ? "other" : p.state === "open" ? "open" : "new";
  return { kind, openAmount, total, usedCount: Number(p.used_count || 0), heldBy: p.held_by ?? null, selectable };
}

/** What the picked receipts pay on this sale: all they hold, or what the sale owes if less. */
export function appliedFromReceipts(openTotal: number, owed: number): number {
  return roundCurrency(Math.max(0, Math.min(openTotal, owed)));
}

/** The part of the M-Pesa amount that no picked receipt or completed STK push stands behind. */
export function uncoveredMpesa(mpesaAmount: number, receiptsOpenTotal: number, stkCompletedAmount: number): number {
  return roundCurrency(Math.max(0, mpesaAmount - receiptsOpenTotal - stkCompletedAmount));
}

/**
 * What a receipt-paid draft sends on submit. Money the cashier took besides the receipts
 * (cash added after the pick) must reach the invoice, so those rows go; when the receipts
 * pay the whole sale there are none, and an empty payments list would be refused as a cash
 * sale with no payment - then nothing is sent and the draft keeps what it has.
 */
export function receiptDraftSubmitData<T extends { paymentMethods: Array<Record<string, unknown>> }>(data: T): T | undefined {
  return data.paymentMethods.some((p) => Number(p.amount) > 0) ? data : undefined;
}

/**
 * Whether a payment mode is M-Pesa - the modes whose money must come from a receipt or an
 * STK push. The server sends its own answer (`is_mpesa`); a server too old to send it
 * falls back to the till's former guess: type Phone, or "mpesa" in the name.
 */
export function isMpesaPaymentMode(mode: { is_mpesa?: boolean; type?: string } | undefined, method: string): boolean {
  if (typeof mode?.is_mpesa === "boolean") return mode.is_mpesa;
  return (mode?.type || "").toLowerCase() === "phone" || /mpesa/i.test(method || "");
}
