import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import BottomNavigation from "../../components/BottomNavigation";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { useDashboardSummary } from "../../hooks/useDashboardSummary";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { formatCurrencyWithSymbol, getCurrencySymbol } from "../../utils/currency";
import {
  contextParts,
  isExternalHref,
  readStoredScope,
  todayIso,
  writeStoredScope,
  type RangeKey,
  type ScopeRequest,
} from "../../utils/dashboardSummary";
import ScopeBar from "./ScopeBar";
import HeroIdentity from "./HeroIdentity";
import MoneyStrip from "./MoneyStrip";
import ExceptionStrip from "./ExceptionStrip";
import PerformanceTier from "./PerformanceTier";

const RANGES: RangeKey[] = ["shift", "today", "week", "month", "custom"];

/**
 * The Sales Dashboard, in three tiers: where the money is, what needs attention, and — second
 * — what sold.
 *
 * Every figure on this page comes from one server call that balances before it is sent. The
 * page it replaces summed a page of invoices in the browser, which is why its revenue and its
 * payment percentages could never agree, and why credit sales appeared in one and not the
 * other.
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const { posDetails } = usePOSProfileStore();
  const company = companyName(posDetails);

  const [request, setRequest] = useState<ScopeRequest>(() => initialScope(company));

  // The company is known only once the profile has loaded; adopt it without discarding a
  // scope the reader has already chosen.
  useEffect(() => {
    if (company) setRequest((current) => (current.company === company ? current : { ...current, company }));
  }, [company]);

  useEffect(() => {
    writeStoredScope(request);
  }, [request]);

  const { summary, isLoading, error, refresh } = useDashboardSummary(request);

  // Switching to Dates with nothing filled in would ask the server for a range that does
  // not exist yet; open on today instead, which the reader then widens.
  const applyScope = (next: ScopeRequest) => {
    if (next.range === "custom" && (!next.dateFrom || !next.dateTo)) {
      const today = todayIso();
      setRequest({ ...next, dateFrom: next.dateFrom || today, dateTo: next.dateTo || today });
      return;
    }
    setRequest(next);
  };

  // Exception rows lead to two different places: pages of this app, and the Desk.
  const openLink = (href: string) => {
    if (isExternalHref(href)) {
      window.location.href = href;
      return;
    }
    navigate(href);
  };

  const symbol = getCurrencySymbol(summary?.identity.currency || posDetails?.currency || "");
  const formatMoney = useMemo(
    () => (amount: number) => formatCurrencyWithSymbol(amount, symbol),
    [symbol]
  );

  return (
    <div className="min-h-screen bg-gray-50 pb-24 dark:bg-gray-900 lg:ml-20 lg:pb-6">
      <header className="border-b border-gray-200 bg-beveren-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white sm:text-2xl">Sales Dashboard</h1>
          <button
            type="button"
            onClick={refresh}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-white dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-4 py-4 sm:px-6">
        <ScopeBar
          request={request}
          availableProfiles={summary?.scope.available_profiles || []}
          onChange={applyScope}
        />

        {error && (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-900/20 dark:text-rose-300">
            {error}
          </p>
        )}

        {!error && !summary && isLoading && (
          <p className="rounded-xl border border-gray-200 bg-white px-4 py-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
            Loading…
          </p>
        )}

        {summary && (
          <div className={isLoading ? "space-y-4 opacity-60 transition-opacity" : "space-y-4"}>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="space-y-4 lg:col-span-2">
                <HeroIdentity
                  identity={summary.identity}
                  context={contextParts(summary, formatMoney)}
                  formatMoney={formatMoney}
                />
                <MoneyStrip
                  rows={summary.collected_by_mode}
                  formatMoney={formatMoney}
                  onNavigate={openLink}
                />
              </div>
              <ExceptionStrip exceptions={summary.exceptions} onNavigate={openLink} />
            </div>

            <PerformanceTier
              performance={summary.performance}
              formatMoney={formatMoney}
              defaultOpen={isDesktop}
            />
          </div>
        )}
      </main>

      {/* The rail already carries navigation on desktop; both at once is two of everything,
          and the bar covers the foot of the page. */}
      {!isDesktop && <BottomNavigation />}
    </div>
  );
}

/** The POS profile reports its company either as a name or as a document. */
function companyName(posDetails: unknown): string | undefined {
  const company = (posDetails as { company?: unknown } | null)?.company;
  if (typeof company === "string") return company || undefined;
  const doc = company as { name?: string; company_name?: string } | undefined;
  return doc?.name || doc?.company_name || undefined;
}

function initialScope(company?: string): ScopeRequest {
  const stored = readStoredScope();
  const range = stored?.range && RANGES.includes(stored.range) ? stored.range : "shift";
  // A stored custom range with an end missing would reopen the page on a prompt rather than
  // on figures; today is the honest starting point, and the reader widens it from there.
  const today = todayIso();
  return {
    range,
    profiles: Array.isArray(stored?.profiles) ? (stored?.profiles as string[]) : [],
    dateFrom: range === "custom" ? stored?.dateFrom || today : stored?.dateFrom,
    dateTo: range === "custom" ? stored?.dateTo || today : stored?.dateTo,
    company,
  };
}
