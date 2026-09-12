import { formatCurrencyWithSymbol } from "../../utils/currency";
import { getEffectiveItemRate, type DiscountMapLike } from "../../utils/cartPricing";
import { roundCurrency } from "../../utils/currencyMath";
import { getItemDiscountTotal, getLineDiscount } from "../../utils/receiptDiscounts";
import { formatTaxLabel, getTaxRateForDisplay } from "../../utils/taxLabel";
import type { Calculations, PaymentAmount } from "./types";
import type { CartItem } from "../../../types";
import DisplayPrintPreview from "../../utils/invoicePrint";

interface InvoicePreviewProps {
  invoiceSubmitted: boolean;
  invoiceData: any;
  submittedInvoice: any;
  externalInvoiceData: any;
  selectedCustomer: any;
  cartItems: CartItem[];
  calculations: Calculations;
  displaySubtotal: number;
  displayTaxTotal: number;
  displayTaxIsIncluded: boolean;
  checkoutGrandTotal: number;
  paymentAmounts: PaymentAmount;
  displayCurrencySymbol: string;
  isB2B: boolean;
  isB2C: boolean;
  currentDate: string;
  /** Per-item discounts and custom rates, needed to resolve the effective rate. */
  itemDiscounts?: DiscountMapLike;
  /** POS Profile is_tax_included_in_basic_rate — decides whether a rate carries tax. */
  isTaxIncludedInBasicRate?: boolean;
  /** Lines the server added that the cart never had, e.g. a delivery charge. */
  extraCharges?: Array<{ item_code: string; amount: number }>;
  /** The server preview's tax rows, which know the rate even with no template picked. */
  taxBreakdown?: Array<{ rate?: number; charge_type?: string }>;
}

/** The rate before any rule or per-item discount.
 *
 * `get_cart_pricing` returns the discounted rate as `price` and keeps the pre-discount
 * rate in `original_price`, so `price` on its own can never tell you a discount was
 * applied. Fall back to `price` when there is no `original_price` - then list and sell
 * agree and nothing is reported as discounted.
 */
function getListRate(item: CartItem) {
  const original = Number((item as CartItem & { original_price?: number }).original_price || 0);
  return original > 0 ? original : Number(item.price || 0);
}

export default function InvoicePreview({
  invoiceSubmitted,
  invoiceData,
  submittedInvoice,
  externalInvoiceData,
  selectedCustomer,
  cartItems,
  calculations,
  displaySubtotal,
  displayTaxTotal,
  displayTaxIsIncluded,
  checkoutGrandTotal,
  paymentAmounts,
  displayCurrencySymbol,
  isB2B,
  isB2C,
  currentDate,
  itemDiscounts = {},
  isTaxIncludedInBasicRate = false,
  extraCharges = [],
  taxBreakdown = [],
}: InvoicePreviewProps) {
  if (invoiceSubmitted && invoiceData) {
    return (
      <div className="mb-4"> 
        <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 text-center">Print Format Preview:</h5>
        <div className="border border-gray-300 dark:border-gray-600 rounded p-2 bg-gray-50 dark:bg-gray-700">
          <DisplayPrintPreview invoice={invoiceData} />
        </div>
      </div>
    );
  }

  // Per-item and rule discounts are already inside the Subtotal, exactly as they are in
  // the cart footer; the row exists so the customer can see what they were given.
  const itemDiscountTotal = getItemDiscountTotal(
    cartItems.map((item) => ({
      quantity: item.quantity,
      listRate: getListRate(item),
      sellRate: getEffectiveItemRate(item, { itemDiscounts, isTaxIncludedInBasicRate }),
    })),
  );
  const totalDiscount = roundCurrency(
    itemDiscountTotal + (calculations.couponDiscount || 0) + (calculations.orderDiscountAmount || 0),
  );
  // selectedTax only exists when a template is picked in the POS; with the company
  // default template the receipt used to print "Tax (% Excl.)" at the customer.
  const taxLabel = formatTaxLabel(
    getTaxRateForDisplay(taxBreakdown, calculations.selectedTax?.rate),
    displayTaxIsIncluded,
  );

  return (
    <>
      <div className="text-center mb-4">
        <h4 className="font-bold text-lg text-gray-900 dark:text-white">KLiK PoS</h4>
        <p className="text-sm text-gray-600 dark:text-gray-400">Sales Invoice</p>
        <p className="text-xs text-gray-500 dark:text-gray-500">{currentDate}</p>
        {isB2B && <p className="text-xs text-orange-600 dark:text-orange-400 font-medium mt-1">Payment Pending</p>}
      </div>

      {selectedCustomer && (
        <div className="mb-4 pb-2 border-b border-gray-200 dark:border-gray-600">
          <p className="font-medium text-gray-900 dark:text-white">{selectedCustomer.name}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">{selectedCustomer.email}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">{selectedCustomer.phone}</p>
        </div>
      )}

      <div className="space-y-2 mb-4">
        {cartItems.length > 0 ? (
          cartItems.map((item, index) => {
            // item.price is the price-list rate. A manually keyed rate, a percentage
            // discount or a discount amount all live elsewhere, so a service item with
            // no price list rendered "0.00" here while the Subtotal below it — which
            // does go through this util — was correct.
            const lineRate = getEffectiveItemRate(item, { itemDiscounts, isTaxIncludedInBasicRate });
            // The cart strikes the list amount through and shows what is charged beneath
            // it; the receipt now agrees.
            const listRate = getListRate(item);
            const discounted = getLineDiscount({ quantity: item.quantity, listRate, sellRate: lineRate }) > 0;
            return (
            <div key={index} className="flex justify-between text-sm">
              <div className="flex-1">
                <p className="font-medium text-gray-900 dark:text-white">{item.name}</p>
                <p className="text-gray-600 dark:text-gray-400">
                  {item.quantity} x {formatCurrencyWithSymbol(lineRate, displayCurrencySymbol)}
                </p>
              </div>
              <div className="text-right">
                {discounted && (
                  <p className="text-xs text-gray-400 line-through">
                    {formatCurrencyWithSymbol(roundCurrency(item.quantity * listRate), displayCurrencySymbol)}
                  </p>
                )}
                <p className="font-medium text-gray-900 dark:text-white">
                  {formatCurrencyWithSymbol(roundCurrency(item.quantity * lineRate), displayCurrencySymbol)}
                </p>
              </div>
            </div>
            );
          })
        ) : (
          <div className="space-y-4">
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Invoice Details</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Invoice #:</span>
                  <span className="font-medium text-gray-900 dark:text-white">{externalInvoiceData?.name || selectedCustomer?.name || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Customer:</span>
                  <span className="font-medium text-gray-900 dark:text-white">{externalInvoiceData?.customer || selectedCustomer?.name || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Total:</span>
                  <span className="font-medium text-gray-900 dark:text-white">
                    {formatCurrencyWithSymbol(externalInvoiceData?.grand_total || calculations.grandTotal, displayCurrencySymbol)}
                  </span>
                </div>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
              <DisplayPrintPreview invoice={externalInvoiceData || submittedInvoice || {}} />
            </div>
          </div>
        )}

        {/* A charge the server adds - a delivery item, say - lands in the Total below.
            Without a line of its own the printed lines do not add up to the printed total. */}
        {extraCharges.map((charge) => (
          <div key={charge.item_code} className="flex justify-between text-sm">
            <div className="flex-1">
              <p className="font-medium text-gray-900 dark:text-white">{charge.item_code}</p>
            </div>
            <p className="font-medium text-gray-900 dark:text-white">
              {formatCurrencyWithSymbol(charge.amount, displayCurrencySymbol)}
            </p>
          </div>
        ))}
      </div>

      <div className="border-t border-gray-200 dark:border-gray-600 pt-2 space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Subtotal</span>
          <span className="text-gray-900 dark:text-white">{formatCurrencyWithSymbol(displaySubtotal, displayCurrencySymbol)}</span>
        </div>
        {totalDiscount > 0 && (
          <div className="flex justify-between text-green-600 dark:text-green-400">
            <span>Discount</span>
            <span>-{formatCurrencyWithSymbol(totalDiscount, displayCurrencySymbol)}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">{taxLabel}</span>
          <span className={`${displayTaxIsIncluded ? "text-blue-600 dark:text-blue-400" : "text-gray-900 dark:text-white"}`}>
            {displayTaxIsIncluded
              ? `(${formatCurrencyWithSymbol(displayTaxTotal, displayCurrencySymbol)})`
              : formatCurrencyWithSymbol(displayTaxTotal, displayCurrencySymbol)}
          </span>
        </div>
        <div className="border-t border-gray-200 dark:border-gray-600 pt-1">
          <div className="flex justify-between font-bold">
            <span className="text-gray-900 dark:text-white">Total</span>
            <span className="text-gray-900 dark:text-white">{formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}</span>
          </div>
        </div>

        {(isB2C || isB2B) && Object.entries(paymentAmounts).filter(([, amount]) => amount > 0).length > 0 && (
          <div className="border-t border-gray-200 dark:border-gray-600 pt-2 mt-2">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Payment Methods:</p>
            {Object.entries(paymentAmounts).filter(([, amount]) => amount > 0).map(([method, amount]) => (
              <div key={method} className="flex justify-between text-xs">
                <span className="text-gray-600 dark:text-gray-400">{method}</span>
                <span className="text-gray-900 dark:text-white">{formatCurrencyWithSymbol(amount, displayCurrencySymbol)}</span>
              </div>
            ))}
          </div>
        )}

        {isB2B && (
          <div className="border-t border-gray-200 dark:border-gray-600 pt-2 mt-2">
            <div className="flex justify-between text-sm">
              <span className="text-orange-600 dark:text-orange-400 font-medium">Outstanding Amount:</span>
              <span className="text-orange-600 dark:text-orange-400 font-bold">{formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}</span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Payment to be collected separately</p>
          </div>
        )}

        {calculations.selectedTax && (
          <div className="border-t border-gray-200 dark:border-gray-600 pt-2 mt-2">
            <p className={`text-xs ${calculations.isInclusive ? "text-blue-500 dark:text-blue-400" : "text-orange-500 dark:text-orange-400"}`}>
              Tax is {calculations.isInclusive ? "inclusive" : "exclusive"} of item prices
            </p>
          </div>
        )}

        {invoiceSubmitted && submittedInvoice?.invoice?.custom_invoice_qr_code && (
          <div className="mt-4 text-center">
            <img src={submittedInvoice.invoice.custom_invoice_qr_code} alt="Invoice QR Code" className="mx-auto w-20 h-20 object-contain border border-gray-200 dark:border-gray-600 rounded-lg" />
          </div>
        )}
      </div>

      <div className="text-center mt-4 pt-2 border-t border-gray-200 dark:border-gray-600">
        <p className="text-xs text-gray-500 dark:text-gray-500">Thank you for your business!</p>
        {isB2B && <p className="text-xs text-orange-500 dark:text-orange-400 mt-1">Invoice will be sent for payment processing</p>}
      </div>
    </>
  );
}
