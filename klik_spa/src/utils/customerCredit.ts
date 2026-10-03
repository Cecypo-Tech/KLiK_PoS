/** The customer-credit tender: open credit notes spent at checkout.

The server lists a customer's open credit notes oldest first
(klik_pos.api.customer_credit.get_customer_credit) and settles the allocations the
checkout payload names (customerCredit) right after submit. This module is the pure
client side of that contract: the fetch, and the oldest-first fill - the same rule
allocateOldestFirst applies to receivable invoices, in the credit-note domain.
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

export interface CreditAllocation {
  invoice: string;
  amount: number;
}

const round2 = (value: number) => Math.round(value * 100) / 100;

/**
 * Fill the wanted amount from the notes in the order given (the server sends oldest
 * first), never exceeding a note's available value or the target. A non-finite `want`
 * allocates nothing - callers pass `Number(inputValue)`.
 */
export function allocateCredit(notes: CreditNote[], want: number): CreditAllocation[] {
  let remaining = round2(Number.isFinite(want) ? Math.max(0, want) : 0);
  const allocations: CreditAllocation[] = [];

  for (const note of notes || []) {
    if (remaining <= 0) break;
    const amount = round2(Math.min(remaining, Math.max(0, note.available)));
    if (amount <= 0) continue;
    allocations.push({ invoice: note.invoice, amount });
    remaining = round2(remaining - amount);
  }

  return allocations;
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
