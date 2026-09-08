import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { fillHourGaps, type DashboardPerformance } from "../../utils/dashboardSummary";

const OPEN_KEY = "dashboard-performance-open";

/**
 * The hourly chart's height, in pixels rather than as a Tailwind class alone.
 *
 * The bars were sized with a percentage height, which collapses to nothing inside a flex
 * column whose own height is content-derived: the chart rendered as an empty band with an
 * axis under it, in both themes. Pixels resolve the same everywhere.
 */
const CHART_HEIGHT = 96;

interface Props {
  performance: DashboardPerformance;
  formatMoney: (amount: number) => string;
  defaultOpen: boolean;
}

/**
 * What sold, when, and who rang it — present, and second. The page it replaces gave a top
 * performer a hero-sized panel of its own while the money questions went unanswered.
 *
 * The bars are plain divs on purpose: a chart library for four horizontal bars is weight the
 * till has to download on every open.
 */
export default function PerformanceTier({ performance, formatMoney, defaultOpen }: Props) {
  const [isOpen, setIsOpen] = useState(() => readOpen() ?? defaultOpen);

  const toggle = () => {
    const next = !isOpen;
    setIsOpen(next);
    writeOpen(next);
  };

  const { kpis, top_items: topItems, cashiers, recent } = performance;
  const hourly = fillHourGaps(performance.hourly);
  const peakHour = Math.max(1, ...hourly.map((bucket) => bucket.amount));
  const topItem = Math.max(1, ...topItems.map((item) => item.amount));
  const topCashier = Math.max(1, ...cashiers.map((row) => row.amount));

  return (
    <section className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-gray-900 dark:text-white"
      >
        Performance
        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="space-y-5 border-t border-gray-100 px-4 py-4 dark:border-gray-700">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi label="Revenue" value={formatMoney(kpis.revenue)} />
            <Kpi label="Sales" value={String(kpis.invoices)} />
            <Kpi label="Average" value={formatMoney(kpis.average)} />
            <Kpi label="Items" value={String(kpis.items)} />
          </div>

          {hourly.length > 0 && (
            <Block title="By hour">
              <div className="flex items-end gap-1" style={{ height: CHART_HEIGHT + 18 }}>
                {hourly.map((bucket) => (
                  <div key={bucket.hour} className="flex flex-1 flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t bg-beveren-500/80"
                      style={{
                        height: Math.max(2, Math.round((bucket.amount / peakHour) * CHART_HEIGHT)),
                      }}
                      title={`${bucket.hour}:00 — ${formatMoney(bucket.amount)}`}
                    />
                    {/* Every third hour, or the axis turns into a wall of digits. */}
                    <span className="text-[10px] text-gray-400">
                      {bucket.hour % 3 === 0 ? bucket.hour : ""}
                    </span>
                  </div>
                ))}
              </div>
            </Block>
          )}

          {/* Three lists, three columns once there is room. Stacked full width they ran the
              page on for screens at a time, which is what pushed the money off the top. */}
          <div className="grid gap-5 lg:grid-cols-3">
          {topItems.length > 0 && (
            <Block title="Top products">
              {topItems.map((item) => (
                <Bar
                  key={item.item_code}
                  label={item.item_name || item.item_code}
                  meta={`${item.qty} sold`}
                  value={formatMoney(item.amount)}
                  ratio={item.amount / topItem}
                />
              ))}
            </Block>
          )}

          {cashiers.length > 0 && (
            <Block title="Cashiers">
              {cashiers.map((row) => (
                <Bar
                  key={row.cashier}
                  label={row.cashier}
                  meta={`${row.count} sale${row.count === 1 ? "" : "s"}`}
                  value={formatMoney(row.amount)}
                  ratio={row.amount / topCashier}
                />
              ))}
            </Block>
          )}

          {recent.length > 0 && (
            <Block title="Recent">
              <ul className="divide-y divide-gray-100 text-sm dark:divide-gray-700">
                {recent.map((invoice) => (
                  <li key={invoice.name} className="flex items-center justify-between gap-2 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-gray-900 dark:text-white">{invoice.name}</p>
                      <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                        {invoice.customer_name} · {invoice.time.slice(0, 5)} · {invoice.mode_of_payment}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 font-medium ${
                        invoice.is_return ? "text-rose-600 dark:text-rose-400" : "text-gray-900 dark:text-white"
                      }`}
                    >
                      {formatMoney(invoice.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </Block>
          )}
          </div>
        </div>
      )}
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-700/40">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="truncate text-base font-semibold text-gray-900 dark:text-white">{value}</p>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Bar({ label, meta, value, ratio }: { label: string; meta: string; value: string; ratio: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="truncate text-gray-900 dark:text-white">{label}</span>
        <span className="shrink-0 text-gray-600 dark:text-gray-300">{value}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-gray-100 dark:bg-gray-700">
        <div
          className="h-1.5 rounded-full bg-beveren-500/70"
          style={{ width: `${Math.max(2, Math.min(100, ratio * 100))}%` }}
        />
      </div>
      <p className="text-xs text-gray-400">{meta}</p>
    </div>
  );
}

function readOpen(): boolean | null {
  try {
    const raw = window.localStorage.getItem(OPEN_KEY);
    return raw === null ? null : raw === "true";
  } catch {
    return null;
  }
}

function writeOpen(value: boolean): void {
  try {
    window.localStorage.setItem(OPEN_KEY, String(value));
  } catch {
    // Remembering the toggle is a nicety, not a requirement.
  }
}
