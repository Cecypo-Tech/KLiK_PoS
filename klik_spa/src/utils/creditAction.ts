/** Choices for return value that cannot go back as cash (the credit router).

Named customers keep the credit (default) or exchange now. Walk In gets no till
choice yet: credit left on Walk In is unclaimable, and the exchange handoff does
not carry a specific note, so until it does both routes need a manager (the
server enforces the same rule - this only decides what the dialog offers).
*/

import type { Customer } from "../types/customer";
import { transformCustomerInfo } from "./transformCustomerInfo";

export type CreditAction = "keep" | "exchange";

export function creditChoices(isWalkin: boolean, hasManagerOverride: boolean): CreditAction[] {
  if (isWalkin && !hasManagerOverride) return [];
  return ["keep", "exchange"];
}

/** The full customer behind a return: the walk-in flag decides the choices, the
object itself feeds the exchange-now cart handoff. Null when the lookup fails -
callers fall back to the safe default (named-customer choices, no handoff). */
export async function fetchReturnCustomer(customerName: string): Promise<Customer | null> {
  try {
    const response = await fetch(
      `/api/method/klik_pos.api.customer.get_customer_info?customer_name=${encodeURIComponent(customerName)}`,
      { credentials: "include" }
    );
    const data = await response.json().catch(() => ({}));
    if (!data.message || data.message.success === false) return null;
    return transformCustomerInfo(data.message, "");
  } catch {
    return null;
  }
}
