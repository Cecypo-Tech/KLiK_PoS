import { localDay } from "../utils/dateRange";

const FIELD =
  "border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-beveren-500 text-gray-900 dark:text-white";

/**
 * A From and a To date ("yyyy-mm-dd", empty = unbounded) with Today and Yesterday quick picks.
 * Today and Yesterday are the till's local days; each sets both ends and shows pressed while
 * it is the range.
 */
export function DateRangeFilter({
  from,
  to,
  onChange,
  size = "py-1.5 text-sm",
  className = "",
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  /** Padding and text size, to match the neighbouring filters. */
  size?: string;
  className?: string;
}) {
  const input = `min-w-0 flex-1 sm:flex-none sm:w-44 px-3 ${size} ${FIELD} bg-white dark:bg-gray-700 dark:[color-scheme:dark]`;
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <input
        type="date"
        aria-label="From date"
        title="From date"
        value={from}
        max={to || undefined}
        onChange={(e) => onChange(e.target.value, to)}
        className={input}
      />
      <span className="text-sm text-gray-500 dark:text-gray-400">to</span>
      <input
        type="date"
        aria-label="To date"
        title="To date"
        value={to}
        min={from || undefined}
        onChange={(e) => onChange(from, e.target.value)}
        className={input}
      />
      {[
        { label: "Today", day: localDay(0) },
        { label: "Yesterday", day: localDay(-1) },
      ].map(({ label, day }) => {
        const active = from === day && to === day;
        return (
          <button
            key={label}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(day, day)}
            className={`px-3 ${size} rounded-lg border whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-beveren-500 ${
              active
                ? "bg-beveren-600 border-beveren-600 text-white"
                : "border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-600"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
