import { formatCurrencyWithSymbol } from "./currency";

/** Why a non-credit sale may not be submitted with this much paid, or null when it may.
 * A till that allows part payment lets a named customer leave a balance; the walk-in
 * customer never carries one, and a sale with nothing paid is a credit sale. */
export function paymentShortfallError({
  total,
  paid,
  allowPartial,
  isWalkin,
  symbol,
}: {
  total: number;
  paid: number;
  allowPartial: boolean;
  isWalkin: boolean;
  symbol: string;
}): string | null {
  if (paid >= total) return null;
  if (allowPartial) {
    if (paid <= 0) return "Enter a payment, or turn on Credit Sale to sell without one.";
    if (isWalkin) return "Part payment needs a named customer to owe the balance. Select the customer first.";
    return null;
  }
  const money = (n: number) => formatCurrencyWithSymbol(n, symbol);
  return `Insufficient payment. Total: ${money(total)}, Paid: ${money(paid)}, Remaining: ${money(total - paid)}`;
}
