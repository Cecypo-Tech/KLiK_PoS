import { Building, User } from "lucide-react";
import type { Customer } from "../../types/customer";

/** Company or person, as the customer box and its search rows show it. */
export function CustomerIcon({ customer, size = 18 }: { customer: Customer; size?: number }) {
  return customer.type === "company"
    ? <Building size={size} className="shrink-0 text-purple-500" aria-hidden />
    : <User size={size} className={`shrink-0 ${customer.type === "walk-in" ? "text-gray-500" : "text-blue-500"}`} aria-hidden />;
}
