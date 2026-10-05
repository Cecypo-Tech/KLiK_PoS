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
