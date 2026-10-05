/** A customer dropdown row's second line: phone | email | town, whichever it has. */
export function customerRowDetails(customer: {
  phone?: string;
  email?: string;
  address?: { city?: string };
}): string {
  return [customer.phone === "N/A" ? "" : customer.phone, customer.email, customer.address?.city]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(" | ");
}
