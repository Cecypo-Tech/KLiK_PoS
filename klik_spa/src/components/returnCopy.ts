import { formatCurrencyWithSymbol } from "../utils/currency";

/** The return window's submit button: the total rides on it, so it never scrolls away. */
export const processReturnLabel = (total: number, symbol: string, loading: boolean): string =>
  loading ? "Processing Return..." : `Process Return · ${formatCurrencyWithSymbol(total, symbol)}`;

/** Where a return goes when no cash was kept from the sale. */
export const creditNoteLine = (total: number, owedOnSale: number, symbol: string): string =>
  owedOnSale > 0 && total <= owedOnSale
    ? `${formatCurrencyWithSymbol(total, symbol)} comes off what the customer owes on this sale.`
    : `${formatCurrencyWithSymbol(total, symbol)} stays as customer credit. Card/M-Pesa refunds go through accounts.`;
