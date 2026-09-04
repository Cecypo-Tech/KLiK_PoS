import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Circle, CheckCircle2, Plus, X } from "lucide-react";
import type { PaymentMethod } from "./types";
import { isReferenceMethod } from "./paymentIcons";
import { partitionPaymentMethods } from "../../utils/paymentMethodVisibility";

interface PaymentMethodsProps {
  paymentMethods: PaymentMethod[];
  invoiceSubmitted: boolean;
  isProcessingPayment: boolean;
  onAmountChange: (methodId: string, amount: string) => void;
  onToggle: (methodId: string) => void;
  onReferenceChange: (methodId: string, value: string) => void;
  setActiveMethodId: (id: string | null) => void;
  references: Record<string, string>;
  headerRight?: ReactNode;
}

export default function PaymentMethods({
  paymentMethods,
  invoiceSubmitted,
  isProcessingPayment,
  onAmountChange,
  onToggle,
  onReferenceChange,
  setActiveMethodId,
  references,
  headerRight,
}: PaymentMethodsProps) {
  const disabled = invoiceSubmitted || isProcessingPayment;

  const [promotedIds, setPromotedIds] = useState<string[]>([]);

  const { rows, tags } = partitionPaymentMethods(
    paymentMethods.map((method, index) => ({
      ...method,
      amount: method.amount || 0,
      isDefault: method.isDefault ?? false,
      idx: method.idx ?? index + 1,
    })),
    promotedIds,
  );

  const [pendingFocusId, setPendingFocusId] = useState<string | null>(null);
  const amountInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const promote = (id: string) => {
    setPromotedIds((current) => [...current, id]);
    setPendingFocusId(id);
  };
  const demote = (id: string) => setPromotedIds((current) => current.filter((x) => x !== id));

  useEffect(() => {
    if (!pendingFocusId) return;
    amountInputRefs.current[pendingFocusId]?.focus();
    setPendingFocusId(null);
  }, [pendingFocusId]);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Payment Methods</h3>
        {headerRight}
      </div>

      <div className="border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-200 dark:divide-gray-700">
        {rows.map((method) => {
          const isActive = (method.amount || 0) > 0;
          const showRef = isActive && isReferenceMethod(method.type, method.name);

          return (
            <div
              key={method.id}
              className={`flex flex-wrap items-center gap-3 px-3 py-2 ${disabled ? "bg-gray-50 dark:bg-gray-800" : ""}`}
            >
              <button
                type="button"
                onClick={() => onToggle(method.id)}
                disabled={disabled}
                title="Use this method (fill outstanding)"
                className={`shrink-0 ${disabled ? "cursor-not-allowed opacity-50" : "hover:text-beveren-600"} ${isActive ? "text-beveren-600" : "text-gray-400"}`}
              >
                {isActive ? <CheckCircle2 size={20} /> : <Circle size={20} />}
              </button>

              <div className={`w-7 h-6 rounded-md ${method.color} text-white flex items-center justify-center shrink-0`}>
                <div className="scale-75">{method.icon}</div>
              </div>

              <span className="flex-1 min-w-[7rem] font-medium text-gray-900 dark:text-white text-sm truncate">
                {method.name}
              </span>

              <input
                ref={(el) => {
                  amountInputRefs.current[method.id] = el;
                }}
                type="number"
                min="0"
                step="0.01"
                value={method.amount || ""}
                onChange={(e) => {
                  setActiveMethodId(method.id);
                  const inputValue = e.target.value;
                  const numValue = inputValue === "" ? 0 : parseFloat(inputValue);
                  onAmountChange(method.id, isNaN(numValue) ? "0" : numValue.toString());
                }}
                onBlur={(e) => {
                  setActiveMethodId(method.id);
                  const numValue = parseFloat(e.target.value);
                  if (!isNaN(numValue)) {
                    onAmountChange(method.id, parseFloat(numValue.toFixed(2)).toString());
                  }
                }}
                placeholder="0.00"
                disabled={disabled}
                className={`w-28 shrink-0 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm text-right ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
              />

              {showRef && (
                <input
                  type="text"
                  value={references[method.id] || ""}
                  onChange={(e) => onReferenceChange(method.id, e.target.value)}
                  placeholder="Reference / Cheque no."
                  disabled={disabled}
                  className={`w-full sm:w-40 shrink-0 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                />
              )}

              {promotedIds.includes(method.id) && !isActive && !disabled && (
                <button
                  type="button"
                  onClick={() => demote(method.id)}
                  aria-label={`Remove ${method.name}`}
                  className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {!disabled && tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {tags.map((method) => (
            <button
              key={method.id}
              type="button"
              onClick={() => promote(method.id)}
              aria-label={`Add ${method.name} as a payment method`}
              className="flex items-center gap-1 rounded-md border border-dashed border-gray-300 dark:border-gray-600 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:border-beveren-500 hover:text-beveren-600 transition-colors"
            >
              <Plus size={13} />
              {method.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
