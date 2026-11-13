import { creditSalesAllowed } from "./creditSales";

/** What the cart is building: a paid sale, a sale on credit, or a quotation. */
export type SaleType = "sale" | "credit" | "quote";

/** A fresh sale starts on credit only when the till allows credit, its Default Sales Type
 * is Credit, and the customer is named (the server refuses credit to a walk-in). */
export function defaultCreditSale(
  profile: { custom_allow_credit_sales_as_pos?: unknown; default_sales_type?: unknown; [key: string]: unknown } | null | undefined,
  customer: unknown,
): boolean {
  const type = typeof profile?.default_sales_type === "string" ? profile.default_sales_type.trim().toLowerCase() : "";
  return creditSalesAllowed(profile) && type === "credit" && (customer as { isWalkin?: number } | null)?.isWalkin !== 1;
}

export const SALE_TYPE_LABEL: Record<SaleType, string> = { sale: "Cash Sale", credit: "Credit Sale", quote: "Quote" };
// The box wears the chosen type's colour: beveren sale, teal credit, amber quote (the bar turns amber too).
export const SALE_TYPE_COLOUR: Record<SaleType, string> = {
  sale: "bg-beveren-600 hover:bg-beveren-700",
  credit: "bg-teal-600 hover:bg-teal-700 dark:bg-teal-500",
  quote: "bg-amber-600 hover:bg-amber-700",
};
