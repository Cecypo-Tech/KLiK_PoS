import { termLabel, type CreditTerms } from "../../utils/creditTerms";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import type { CustomerBalance } from "../../stores/cartStore";

export interface CreditSaleCardProps {
  customerName: string;
  terms: CreditTerms | null;
  termsTemplate: string;
  onSelectTerm: (name: string) => void;
  dueDate: string;
  onDueDateChange: (date: string) => void;
  disabled: boolean;
  currencySymbol: string;
  /** What the customer owes; only on tills that show overdue warnings. */
  balance?: CustomerBalance | null;
}

const FIELD =
  "px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm disabled:cursor-not-allowed disabled:opacity-50";

/** A credit sale's when-to-pay: Payment Terms when the site has them, else a due date. */
export default function CreditSaleCard({
  customerName, terms, termsTemplate, onSelectTerm, dueDate, onDueDateChange, disabled, currencySymbol, balance,
}: CreditSaleCardProps) {
  const templates = terms?.templates ?? [];
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-950/30">
      <div>
        <h3 className="text-sm font-semibold text-teal-900 dark:text-teal-200">Credit sale · {customerName}</h3>
        {balance && (
          <p className="text-xs text-gray-700 dark:text-gray-300">
            Owes {formatCurrencyWithSymbol(balance.outstanding, currencySymbol)}
            {balance.overdue > 0 && (
              <span className="text-red-600 dark:text-red-400"> · {formatCurrencyWithSymbol(balance.overdue, currencySymbol)} overdue</span>
            )}
          </p>
        )}
      </div>
      {templates.length > 0 ? (
        <div className="flex items-center gap-2">
          <label htmlFor="pos-credit-terms" className="text-sm font-medium text-gray-700 dark:text-gray-300">Terms</label>
          <select
            id="pos-credit-terms"
            value={termsTemplate}
            onChange={(e) => onSelectTerm(e.target.value)}
            disabled={disabled}
            className={`max-w-[16rem] ${FIELD}`}
          >
            {templates.map((term) => (
              <option key={term.name} value={term.name}>{termLabel(term)}</option>
            ))}
          </select>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <label htmlFor="pos-credit-due-date" className="text-sm font-medium text-gray-700 dark:text-gray-300">Due Date</label>
          <input
            id="pos-credit-due-date"
            type="date"
            value={dueDate}
            onChange={(e) => onDueDateChange(e.target.value)}
            min={new Date().toISOString().split("T")[0]}
            disabled={disabled}
            className={FIELD}
          />
        </div>
      )}
    </div>
  );
}
