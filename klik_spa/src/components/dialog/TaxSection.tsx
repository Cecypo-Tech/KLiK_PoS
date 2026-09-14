import { selectAllOnFocus } from "../../utils/selectAllOnFocus";

interface TaxSectionProps {
  invoiceSubmitted: boolean;
  isProcessingPayment: boolean;
  allowDiscountChange: boolean;
  orderDiscountAmount: number;
  orderDiscountPercentInput: number;
  onOrderDiscountAmountChange: (value: number) => void;
  onOrderDiscountPercentChange: (value: number) => void;
}

/**
 * The order-level discount inputs. They sit in one row with loyalty and the delivery
 * charge; the customer's Tax ID lives in the cart's additional customer info instead.
 */
export default function TaxSection({
  invoiceSubmitted,
  isProcessingPayment,
  allowDiscountChange,
  orderDiscountAmount,
  orderDiscountPercentInput,
  onOrderDiscountAmountChange,
  onOrderDiscountPercentChange,
}: TaxSectionProps) {
  if (!allowDiscountChange) return null;

  const locked = invoiceSubmitted || isProcessingPayment;

  return (
    <div className="min-w-[10rem] flex-1">
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Discount</label>
      <div className="grid grid-cols-2 gap-1.5">
        <input
          type="number"
          min="0"
          step="0.01"
          placeholder="Amount"
          value={orderDiscountAmount || ""}
          {...selectAllOnFocus}
          onChange={(e) => onOrderDiscountAmountChange(Number(e.target.value || 0))}
          disabled={locked}
          className={`w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`}
        />
        <input
          type="number"
          min="0"
          max="100"
          step="0.1"
          placeholder="%"
          value={orderDiscountPercentInput || ""}
          {...selectAllOnFocus}
          onChange={(e) => onOrderDiscountPercentChange(Number(e.target.value || 0))}
          disabled={locked}
          className={`w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`}
        />
      </div>
    </div>
  );
}
