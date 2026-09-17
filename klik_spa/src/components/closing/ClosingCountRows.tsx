import { Banknote, CreditCard } from "lucide-react";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import { selectAllOnFocus } from "../../utils/selectAllOnFocus";

export interface ClosingCountStat {
  name: string;
  openingAmount: number;
  amount: number;
  transactions: number;
}

interface ClosingCountRowsProps {
  stats: ClosingCountStat[];
  counted: Record<string, number>;
  onCountChange: (modeName: string, value: string) => void;
  currency: string;
  /** The till's blind-count setting: the cashier counts without seeing what is expected. */
  hideExpected: boolean;
  varianceClass: (variance: number) => string;
}

/**
 * One compact line per mode of payment on the Close Shift dialog, so a till with many
 * modes fits without scrolling. Expected and Variance are left out on a blind-count till.
 */
export default function ClosingCountRows({
  stats,
  counted,
  onCountChange,
  currency,
  hideExpected,
  varianceClass,
}: ClosingCountRowsProps) {
  const cols = hideExpected
    ? "grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)]"
    : "grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))]";
  const money = (value: number) => formatCurrencyWithSymbol(value, currency);

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 text-sm">
      <div
        className={`grid ${cols} gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-700/60 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400 sticky top-0`}
      >
        <span>Mode</span>
        <span className="text-right">Opening</span>
        {!hideExpected && <span className="text-right">Expected</span>}
        <span className="text-right">Counted</span>
        {!hideExpected && <span className="text-right">Variance</span>}
      </div>
      <div className="divide-y divide-gray-100 dark:divide-gray-700">
        {stats.map((stat) => {
          const variance = (counted[stat.name] || 0) - stat.amount;
          const isCash = stat.name.toLowerCase().includes("cash");
          return (
            <div key={stat.name} className={`grid ${cols} gap-2 items-center px-3 py-1.5`}>
              <div className="flex items-center gap-2 min-w-0">
                {isCash ? (
                  <Banknote className="w-4 h-4 shrink-0 text-green-600" />
                ) : (
                  <CreditCard className="w-4 h-4 shrink-0 text-beveren-600" />
                )}
                <span className="truncate font-medium text-gray-900 dark:text-white" title={stat.name}>
                  {stat.name}
                </span>
                <span className="shrink-0 text-xs text-gray-400" title="Transactions">
                  ×{stat.transactions}
                </span>
              </div>
              <span className="text-right tabular-nums text-gray-600 dark:text-gray-300">
                {money(stat.openingAmount)}
              </span>
              {!hideExpected && (
                <span className="text-right tabular-nums font-medium text-gray-900 dark:text-white">
                  {money(stat.amount)}
                </span>
              )}
              <input
                type="number"
                step="0.01"
                inputMode="decimal"
                placeholder="0.00"
                aria-label={`Counted ${stat.name}`}
                value={counted[stat.name] || ""}
                onChange={(e) => onCountChange(stat.name, e.target.value)}
                {...selectAllOnFocus}
                className="h-8 w-full min-w-0 px-2 text-right tabular-nums border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
              {!hideExpected && (
                <span className={`text-right tabular-nums font-semibold ${varianceClass(variance)}`}>
                  {money(variance)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
