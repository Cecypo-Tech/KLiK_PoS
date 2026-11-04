"use client";

import { formatCurrencyWithSymbol } from "../../utils/currency";

interface OrderSummaryFooterProps {
  subtotal: number;
  total: number;
  totalItemDiscount: number;
  couponDiscount: number;
  onCheckout: () => void;
  onClearCart: () => void;
  isValidating: boolean;
  isMobile?: boolean;
  currency_symbol?: string;
  taxExclusive?: boolean;
  /** Formatted total net weight, e.g. "12.5 Kg"; empty hides the row. */
  netWeightLabel?: string;
  /** Quoting: the main button saves a quote instead of checking out, and Quote hides. */
  quoteMode?: boolean;
  onQuote?: () => void;
}

export const OrderSummaryFooter = ({
  subtotal,
  total,
  totalItemDiscount,
  couponDiscount,
  onCheckout,
  onClearCart,
  isValidating,
  isMobile,
  currency_symbol,
  taxExclusive = false,
  netWeightLabel = "",
  quoteMode = false,
  onQuote,
}: OrderSummaryFooterProps) => {
  const discount = totalItemDiscount + couponDiscount;

  return (
    <div
      className={`${
        isMobile
          ? "flex-shrink-0 p-3 bg-white dark:bg-gray-800 border-t border-gray-100 dark:border-gray-700 shadow-lg"
          : "p-4 border-t border-gray-100 dark:border-gray-700"
      } space-y-3`}
    >
      {/* Summary */}
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Subtotal</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {formatCurrencyWithSymbol(subtotal, currency_symbol)}
          </span>
        </div>
        {discount > 0 && (
          <div className="flex justify-between text-green-600 dark:text-green-400">
            <span>Discount</span>
            <span>-{formatCurrencyWithSymbol(discount, currency_symbol)}</span>
          </div>
        )}
        {netWeightLabel && (
          <div className="flex justify-between text-gray-500 dark:text-gray-400">
            <span>Net Weight</span>
            <span className="tabular-nums">{netWeightLabel}</span>
          </div>
        )}
      </div>

      {/* Hold lives in checkout (Shift+F10 opens it, again holds). */}
      <div className="flex gap-3">
        <button
          id="pos-clear-cart-btn"
          onClick={onClearCart}
          className={`shrink-0 px-3 border border-red-500 text-red-600 dark:text-red-400 rounded-xl font-medium hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors text-sm ${
            isMobile ? "py-3" : "py-2"
          }`}
        >
          Clear Cart
        </button>
        {!quoteMode && onQuote && (
          <button
            id="pos-quote-btn"
            onClick={onQuote}
            className={`shrink-0 px-3 border border-amber-500 text-amber-700 dark:text-amber-400 rounded-xl font-medium hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors text-sm ${
              isMobile ? "py-3" : "py-2"
            }`}
          >
            Quote
          </button>
        )}
        <button
          id="pos-checkout-btn"
          onClick={onCheckout}
          disabled={isValidating}
          className={`flex-1 min-w-0 ${
            quoteMode ? "bg-amber-600 hover:bg-amber-700" : "bg-beveren-600 hover:bg-beveren-700"
          } text-white rounded-xl font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
            isMobile ? "py-3 text-base" : "py-2 text-sm"
          }`}
        >
          {quoteMode
            ? isValidating ? "Saving quote..." : `Save Quote ${formatCurrencyWithSymbol(total, currency_symbol)}${taxExclusive ? " +" : ""}`
            : isValidating
            ? "Checking cart..."
            : `Checkout ${formatCurrencyWithSymbol(total, currency_symbol)}${taxExclusive ? " +" : ""}`}
        </button>
      </div>
    </div>
  );
};