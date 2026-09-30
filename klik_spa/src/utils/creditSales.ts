/**
 * Whether the checkout offers "Is Credit Sale": the till's "Allow Credit Sales" checkbox.
 * The server refuses a credit sale from a till without it, so this only keeps the button
 * honest. "Allow Partial Payment" is about part-paying ordinary sales, and "Allow Credit
 * Sales as POS Sales" only decides whether an allowed credit sale is marked is_pos.
 */
export function creditSalesAllowed(
  profile: { custom_allow_credit_sales?: unknown; [key: string]: unknown } | null | undefined,
): boolean {
  return Boolean(Number(profile?.custom_allow_credit_sales || 0));
}
