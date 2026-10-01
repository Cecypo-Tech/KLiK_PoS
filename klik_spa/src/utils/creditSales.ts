/**
 * Whether the checkout offers "Is Credit Sale": the till's one "Allow Credit Sales" checkbox
 * (custom_allow_credit_sales_as_pos). The server refuses a credit sale from a till without it,
 * so this only keeps the button honest. "Allow Partial Payment" is about part-paying ordinary
 * sales. The second, newer custom_allow_credit_sales checkbox is gone.
 */
export function creditSalesAllowed(
  profile: { custom_allow_credit_sales_as_pos?: unknown; [key: string]: unknown } | null | undefined,
): boolean {
  return Boolean(Number(profile?.custom_allow_credit_sales_as_pos || 0));
}
