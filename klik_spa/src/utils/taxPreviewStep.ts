export interface TaxPreviewState {
  isOpen: boolean;
  invoiceSubmitted: boolean;
  hasCustomer: boolean;
  cartCount: number;
}

/**
 * What the checkout does with the server's tax preview on each change.
 *
 * Once the sale is submitted the last preview is kept, not cleared: it describes exactly the
 * cart that was sold, and without it the completed screen falls back to local arithmetic
 * that knows nothing of the server's tax - it showed the pre-tax amount as the grand total
 * and the tax as "change due".
 */
export function taxPreviewStep(s: TaxPreviewState): "fetch" | "keep" | "clear" {
  if (!s.isOpen) return "clear";
  // Printing from the completed screen empties the cart behind it; the totals shown must
  // still be the sale's, until the checkout closes.
  if (s.invoiceSubmitted) return "keep";
  if (!s.hasCustomer || s.cartCount === 0) return "clear";
  return "fetch";
}
