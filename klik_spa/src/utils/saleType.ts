import { creditSalesAllowed } from "./creditSales";

/** What the cart is building: a paid sale, a sale on credit, or a quotation. */
export type SaleType = "sale" | "credit" | "quote";

/** A fresh sale starts on credit only when the till allows credit, its Default Sales Type
 * is Credit, and the customer is named (the server refuses credit to a walk-in). */
export function defaultCreditSale(
  profile: { custom_allow_credit_sales_as_pos?: unknown; default_sales_type?: unknown; [key: string]: unknown } | null | undefined,
  customer: { isWalkin?: number } | null | undefined,
): boolean {
  const type = typeof profile?.default_sales_type === "string" ? profile.default_sales_type.trim().toLowerCase() : "";
  return creditSalesAllowed(profile) && type === "credit" && customer?.isWalkin !== 1;
}
