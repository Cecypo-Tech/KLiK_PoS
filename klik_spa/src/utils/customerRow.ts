import type { Customer } from "../types/customer";
/** A customer dropdown row's second line: phone | email | PIN | town, whichever it has. */
export function customerRowDetails(customer: {
  phone?: string;
  email?: string;
  taxId?: string;
  address?: { city?: string };
}): string {
  return [
    customer.phone === "N/A" ? "" : customer.phone,
    customer.email,
    customer.taxId ? `PIN: ${customer.taxId}` : "",
    customer.address?.city,
  ]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(" | ");
}

/** Company or VIP pill beside a customer's name. */
export function customerBadge(customer: Customer): { label: string; color: string } | null {
  if (customer.type === "company") {
    return { label: "Company", color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" };
  }
  if (customer.status === "vip") {
    return { label: "VIP", color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" };
  }
  return null;
}
