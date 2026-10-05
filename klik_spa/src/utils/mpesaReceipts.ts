import type { MpesaRegisterPayment } from "../services/mpesa";
import { formatCurrencyWithSymbol } from "./currency";
import { roundCurrency } from "./currencyMath";
import { localDay } from "./dateRange";
import { formatDateOnly } from "./time";

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
 * The receipts picked at checkout, as the submit carries them. The pick itself writes nothing:
 * the server records them on the invoice only when the sale is submitted, so an abandoned
 * receipt checkout uses no invoice number.
 */
export function receiptPicksPayload(
  flow: { source: "stk" | "c2b"; modeOfPayment: string; c2bPayments?: Array<{ name: string }> } | null,
): { mode_of_payment: string; payments: string[] } | null {
  if (flow?.source !== "c2b" || !flow.c2bPayments?.length) return null;
  return { mode_of_payment: flow.modeOfPayment, payments: flow.c2bPayments.map((p) => p.name) };
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

/** The note after a sale that left money on its M-Pesa receipt(s) for the customer's next sale. */
export function receiptLeftoverMessage(amount: number, currencySymbol: string, who: string): string {
  return `${formatCurrencyWithSymbol(amount, currencySymbol)} stays on the M-Pesa receipt for ${who}'s next sale. No cash change is given for M-Pesa.`;
}

/**
 * When the customer paid, for the receipt card: Safaricom's transtime ("YYYYMMDDHHmmss") as
 * date and time, else the row's posting date. `today` says whether it is the till's today -
 * an older receipt is more likely one a cashier should look at twice.
 */
export function receiptPaidAt(
  payment: Pick<MpesaRegisterPayment, "transtime" | "posting_date">,
  today: string = localDay(0),
): { label: string; today: boolean } | null {
  const t = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})\d{2}$/.exec(payment.transtime || "");
  const day = t ? `${t[1]}-${t[2]}-${t[3]}` : (payment.posting_date || "").slice(0, 10);
  if (!day) return null;
  const label = t ? `${formatDateOnly(day)} ${t[4]}:${t[5]}` : formatDateOnly(day);
  return { label, today: day === today };
}

/**
 * The tender rows a submit records as payments. Picked receipts reach the invoice as advances,
 * so their M-Pesa row is left out - of the rows and of the amount paid alike, or the server
 * counts that money twice.
 */
export function tenderSent<T extends { method: string; amount: number }>(rows: T[], receiptMethod?: string | null): T[] {
  return receiptMethod ? rows.filter((row) => row.method !== receiptMethod) : rows;
}
