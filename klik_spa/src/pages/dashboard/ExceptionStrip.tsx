import { AlertTriangle, ChevronRight, CheckCircle2 } from "lucide-react";
import { exceptionHref, exceptionLabel, type ExceptionRow } from "../../utils/dashboardSummary";

interface Props {
  exceptions: ExceptionRow[];
  /** True when these counts reach beyond the tills the reader selected. */
  coversMoreThanScope: boolean;
  onNavigate: (href: string) => void;
}

/**
 * Only what is wrong, and only when something is. Each row is the reason the reader used to
 * leave this page for Invoice History or the M-Pesa register, so each row goes there with
 * the filter already applied.
 */
export default function ExceptionStrip({ exceptions, coversMoreThanScope, onNavigate }: Props) {
  if (exceptions.length === 0) {
    return (
      <section className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
        All clear
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="border-b border-gray-100 px-4 py-3 dark:border-gray-700">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          Needs attention
        </h2>
        {coversMoreThanScope && (
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Across all tills, including any that were renamed or removed
          </p>
        )}
      </div>
      <ul className="divide-y divide-gray-100 dark:divide-gray-700">
        {exceptions.map((row) => {
          const href = exceptionHref(row);
          const label = exceptionLabel(row);
          return (
            <li key={row.key}>
              {href ? (
                <button
                  type="button"
                  onClick={() => onNavigate(href)}
                  className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  <span>{label}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
                </button>
              ) : (
                <p className="px-4 py-3 text-sm text-gray-700 dark:text-gray-200">{label}</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
