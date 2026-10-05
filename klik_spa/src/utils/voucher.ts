/** Store-credit vouchers at the till: a credit note's number plus its original sale's.

The server looks a voucher up (klik_pos.api.customer_credit.lookup_credit_voucher) and
re-checks every applied voucher at checkout; these helpers only decide what the till
offers and how much it applies. */

export type VoucherStatus = "open" | "partly_used" | "used" | "cancelled" | "no_match";

export interface VoucherLookup {
  status: VoucherStatus;
  note?: string;
  original?: string;
  customer?: string;
  customer_name?: string;
  is_walkin?: boolean;
  company?: string;
  currency?: string;
  total?: number;
  available?: number;
  walkin_name?: string | null;
  walkin_phone?: string | null;
}

export interface AppliedVoucher {
  note: string;
  /** The original sale number - the server requires it for a Walk In voucher. */
  original: string | null;
  amount: number;
  /** What the voucher held when applied - the most it can pay. */
  available?: number;
}

export type VoucherCustomerRule = "apply" | "switch" | "refuse_named" | "refuse_walkin";

const round2 = (value: number) => Math.round(value * 100) / 100;

export function voucherStatusLabel(lookup: VoucherLookup, money: (value: number) => string): string {
  switch (lookup.status) {
    case "open":
      return `Open: ${money(lookup.available ?? 0)} available`;
    case "partly_used":
      return `Partly used: ${money(lookup.available ?? 0)} left of ${money(lookup.total ?? 0)}`;
    case "used":
      return "Nothing left (used or refunded)";
    case "cancelled":
      return "Cancelled";
    default:
      return "No voucher matches these numbers";
  }
}

export function isUsable(lookup: VoucherLookup | null): boolean {
  return Boolean(
    lookup && (lookup.status === "open" || lookup.status === "partly_used") && (lookup.available ?? 0) > 0,
  );
}

/** Payment Reconciliation only settles a customer's own invoices: who may use which voucher.
A Walk In voucher pays only its own Walk In customer's sales - the server compares the two. */
export function voucherCustomerRule(
  sale: { customer: string; isWalkin: boolean },
  voucher: { customer: string; isWalkin: boolean },
): VoucherCustomerRule {
  if (voucher.isWalkin) return sale.isWalkin && voucher.customer === sale.customer ? "apply" : "refuse_walkin";
  if (voucher.customer === sale.customer) return "apply";
  return sale.isWalkin ? "switch" : "refuse_named";
}

export function appliedTotal(applied: AppliedVoucher[]): number {
  return round2(applied.reduce((sum, voucher) => sum + voucher.amount, 0));
}

/** What a voucher pays: what the sale still needs, up to what the voucher holds. */
export function voucherApplyAmount(available: number, payable: number, alreadyApplied: number): number {
  return round2(Math.max(0, Math.min(available, payable - alreadyApplied)));
}

export function addVoucher(applied: AppliedVoucher[], next: AppliedVoucher): AppliedVoucher[] {
  if (next.amount <= 0 || applied.some((voucher) => voucher.note === next.note)) return applied;
  return [...applied, next];
}

/** The cashier's own amount for an applied voucher: no more than it holds, nor than the sale
still owes after the other vouchers. Nothing drops it. */
export function resizeVoucher(applied: AppliedVoucher[], note: string, amount: number, payable: number): AppliedVoucher[] {
  const others = appliedTotal(applied.filter((voucher) => voucher.note !== note));
  return applied
    .map((voucher) => {
      if (voucher.note !== note) return voucher;
      const most = Math.min(voucher.available ?? voucher.amount, payable - others);
      return { ...voucher, amount: round2(Math.max(0, Math.min(amount, most))) };
    })
    .filter((voucher) => voucher.amount > 0);
}

/** Vouchers never outgrow the sale: the last applied shrinks first, and one shrunk to
nothing is dropped. */
export function capVouchers(applied: AppliedVoucher[], payable: number): AppliedVoucher[] {
  let excess = round2(appliedTotal(applied) - Math.max(0, payable));
  if (excess <= 0) return applied;
  const capped: AppliedVoucher[] = [];
  for (const voucher of [...applied].reverse()) {
    const take = Math.min(voucher.amount, excess);
    excess = round2(excess - take);
    capped.unshift({ ...voucher, amount: round2(voucher.amount - take) });
  }
  return capped.filter((voucher) => voucher.amount > 0);
}

export interface TenderRow {
  method: string;
  amount: number;
}

/** With vouchers applied, the payment rows as the drawer keeps them: cash net of the change
handed back. ERPNext books change only when the paid amount exceeds the total, which a
voucher sale never does (the vouchers are no payment row), so the change comes off the cash
here - the cash row last edited first, then the other cash rows from the last. What no cash
row can absorb (an overpaid card, say) is `unabsorbed`. Without vouchers nothing changes. */
export function netOfChange(
  rows: TenderRow[],
  vouchersTotal: number,
  payable: number,
  isCash: (method: string) => boolean,
  lastEdited: string | null = null,
): { rows: TenderRow[]; unabsorbed: number } {
  if (vouchersTotal <= 0) return { rows, unabsorbed: 0 };
  let excess = round2(rows.reduce((sum, row) => sum + row.amount, 0) + vouchersTotal - payable);
  if (excess <= 0) return { rows, unabsorbed: 0 };
  const netted = rows.map((row) => ({ ...row }));
  const cashOrder = netted
    .filter((row) => isCash(row.method))
    .reverse()
    .sort((a, b) => Number(b.method === lastEdited) - Number(a.method === lastEdited));
  for (const row of cashOrder) {
    if (excess <= 0) break;
    const take = Math.min(Math.max(0, row.amount), excess);
    row.amount = round2(row.amount - take);
    excess = round2(excess - take);
  }
  return { rows: netted, unabsorbed: excess };
}

/** The payment amounts as a person reads them: the vouchers' internal key shown as
"Vouchers" - or "Vouchers (store credit)" beside a real mode of payment of that name. */
export function labelVoucherAmounts(amounts: Record<string, number>, key: string): Record<string, number> {
  if (!(key in amounts)) return amounts;
  const { [key]: vouchers, ...rows } = amounts;
  const label = "Vouchers" in rows ? "Vouchers (store credit)" : "Vouchers";
  return { ...rows, [label]: vouchers ?? 0 };
}

/** Why this sale cannot carry vouchers right now, or null when it can - a bare phrase the
dialog puts after "Vouchers removed:" or "Vouchers unavailable:". */
export function vouchersBlockedReason(state: { isCreditSale: boolean; editingDraft: boolean }): string | null {
  if (state.isCreditSale) return "this is a credit sale";
  if (state.editingDraft) return "this sale is finishing an older draft";
  return null;
}

/**
 * Why the vouchers cannot change now, or null. Once an M-Pesa request went out it asked the
 * customer for what the vouchers left: a voucher added or resized after it would overpay the sale.
 */
export function vouchersLockedByPush(pushMethod: string | null | undefined): string | null {
  return pushMethod
    ? "Apply vouchers before sending the M-Pesa request - it already asked the customer for this amount."
    : null;
}

/**
 * A sale's vouchers belong to its customer: once the customer changes, they start over. Not
 * after submit - printing the receipt empties the cart, customer and all, behind it.
 */
export function customerChangeDropsVouchers(
  previousId: string | null,
  nextId: string | null,
  appliedCount: number,
  submitted = false,
): boolean {
  return !submitted && appliedCount > 0 && previousId !== null && previousId !== nextId;
}
