/** A named customer's open credit notes - the vouchers the till lists without typing.

The server lists them oldest first (klik_pos.api.customer_credit.get_customer_credit);
Walk In credit is never listed. This module is the client side of that listing: the fetch
and its types.
*/

export interface CreditNote {
  invoice: string;
  posting_date?: string;
  available: number;
}

export interface CustomerCredit {
  total: number;
  notes: CreditNote[];
}

/** What `customer` can spend at this company's till, oldest note first. */
export async function fetchCustomerCredit(
  customer: string,
  company: string,
  currency?: string
): Promise<CustomerCredit> {
  const params = new URLSearchParams({ customer, company });
  if (currency) params.set("currency", currency);
  const response = await fetch(
    `/api/method/klik_pos.api.customer_credit.get_customer_credit?${params.toString()}`,
    { credentials: "include" }
  );
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.message) {
    throw new Error(`Could not load customer credit (server answered ${response.status})`);
  }
  return result.message as CustomerCredit;
}
