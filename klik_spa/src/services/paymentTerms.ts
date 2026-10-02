import type { CreditTerms } from "../utils/creditTerms";

/** Payment terms the till offers a credit sale for `customer`, and the one to preselect. */
export async function getCreditTerms(customer: string | undefined): Promise<CreditTerms> {
  const query = customer ? `?customer=${encodeURIComponent(customer)}` : "";
  const response = await fetch(`/api/method/klik_pos.api.payment_terms.credit_terms${query}`, {
    credentials: "include",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.message) {
    throw new Error(`Could not load payment terms (server answered ${response.status})`);
  }
  return result.message as CreditTerms;
}
