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

/** Payment Reconciliation only settles a customer's own invoices: who may use which voucher. */
export function voucherCustomerRule(
  sale: { customer: string; isWalkin: boolean },
  voucher: { customer: string; isWalkin: boolean },
): VoucherCustomerRule {
  if (voucher.isWalkin) return sale.isWalkin ? "apply" : "refuse_walkin";
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

/** Why this sale cannot carry vouchers right now, or null when it can. */
export function vouchersBlockedReason(state: {
  isCreditSale: boolean;
  mpesaOrder: boolean;
  editingDraft: boolean;
}): string | null {
  if (state.isCreditSale) return "a credit sale is paid later, not with vouchers";
  if (state.mpesaOrder) return "vouchers can't be combined with an M-Pesa order";
  if (state.editingDraft) return "vouchers can't be used when finishing an older draft";
  return null;
}
