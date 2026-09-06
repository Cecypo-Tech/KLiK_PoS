import { ArrowRight } from "lucide-react";
import { collapseModeRows, unmatchedHref, type ModeRow } from "../../utils/dashboardSummary";

interface Props {
  rows: ModeRow[];
  formatMoney: (amount: number) => string;
  onNavigate: (href: string) => void;
}

/**
 * One line per mode of payment: what it took, what arrived later, how many sales.
 *
 * A line each, not a panel each — the previous payment panel spent the page's whole width
 * on four modes and a bar chart of percentages that excluded every credit sale.
 */
export default function MoneyStrip({ rows, formatMoney, onNavigate }: Props) {
  const { rows: visible, collapsed } = collapseModeRows(rows);

  return (
    <section className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <h2 className="border-b border-gray-100 px-4 py-3 text-sm font-semibold text-gray-900 dark:border-gray-700 dark:text-white">
        Collected by method
      </h2>

      {visible.length === 0 && (
        <p className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">Nothing collected yet.</p>
      )}

      <ul className="divide-y divide-gray-100 dark:divide-gray-700">
        {visible.map((row) => {
          const href = unmatchedHref(row);
          return (
            <li key={row.mode} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-900 dark:text-white">{row.mode}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {row.count} sale{row.count === 1 ? "" : "s"}
                  {row.later ? ` · ${formatMoney(row.later)} on account` : ""}
                </p>
                {href && (
                  <button
                    type="button"
                    onClick={() => onNavigate(href)}
                    className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-300"
                  >
                    {row.unmatched} unmatched · {formatMoney(row.unmatched_amount || 0)}
                    <ArrowRight className="h-3 w-3" />
                  </button>
                )}
              </div>
              <p className="shrink-0 text-sm font-semibold text-gray-900 dark:text-white">
                {formatMoney(row.amount + row.later)}
              </p>
            </li>
          );
        })}

        {collapsed.length > 0 && (
          <li className="flex items-center justify-between px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
            <span className="truncate">{collapsed.join(" · ")}</span>
            <span>{formatMoney(0)}</span>
          </li>
        )}
      </ul>
    </section>
  );
}
