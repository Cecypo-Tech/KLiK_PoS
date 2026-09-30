import { selectAllOnFocus } from "../../utils/selectAllOnFocus";
import StepperInput from "../common/StepperInput";

interface TaxSectionProps {
  invoiceSubmitted: boolean;
  isProcessingPayment: boolean;
  allowDiscountChange: boolean;
  orderDiscountAmount: number;
  orderDiscountPercentInput: number;
  onOrderDiscountAmountChange: (value: number) => void;
  onOrderDiscountPercentChange: (value: number) => void;
  /** Label beside compact inputs, for the Other charges card. */
  inline?: boolean;
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
  inline = false,
}: TaxSectionProps) {
  if (!allowDiscountChange) return null;

  const locked = invoiceSubmitted || isProcessingPayment;

  const inputClass = `px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`;

  if (inline) {
    return (
      <div className="flex items-center justify-between gap-3">
        <label className="text-sm font-medium text-gray-600 dark:text-gray-400">Discount</label>
        <div className="flex gap-1.5">
          <StepperInput
            min="0"
            step="0.01"
            placeholder="Amount"
            aria-label="Discount amount"
            value={orderDiscountAmount || ""}
            {...selectAllOnFocus}
            onChange={(e) => onOrderDiscountAmountChange(Number(e.target.value || 0))}
            onStep={onOrderDiscountAmountChange}
            disabled={locked}
            wrapperClassName="w-32"
            className={`w-full text-right ${inputClass}`}
          />
          <StepperInput
            min="0"
            max="100"
            step="0.1"
            placeholder="%"
            aria-label="Discount percent"
            value={orderDiscountPercentInput || ""}
            {...selectAllOnFocus}
            onChange={(e) => onOrderDiscountPercentChange(Number(e.target.value || 0))}
            onStep={onOrderDiscountPercentChange}
            maxValue={100}
            disabled={locked}
            wrapperClassName="w-24"
            className={`w-full text-right ${inputClass}`}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-w-[10rem] flex-1">
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Discount</label>
      {/* One per row: each field keeps room for its digits beside the arrows. */}
      <div className="grid grid-cols-1 gap-1.5">
        <StepperInput
          min="0"
          step="0.01"
          placeholder="Amount"
          value={orderDiscountAmount || ""}
          {...selectAllOnFocus}
          onChange={(e) => onOrderDiscountAmountChange(Number(e.target.value || 0))}
          onStep={onOrderDiscountAmountChange}
          disabled={locked}
          className={`w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`}
        />
        <StepperInput
          min="0"
          max="100"
          step="0.1"
          placeholder="%"
          value={orderDiscountPercentInput || ""}
          {...selectAllOnFocus}
          onChange={(e) => onOrderDiscountPercentChange(Number(e.target.value || 0))}
          onStep={onOrderDiscountPercentChange}
          maxValue={100}
          disabled={locked}
          className={`w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`}
        />
      </div>
    </div>
  );
}
