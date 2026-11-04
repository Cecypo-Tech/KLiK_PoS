import { useEffect, useRef, useState } from "react";
import { Calendar, ChevronDown, Search } from "lucide-react";
import { RANGE_LABELS, type RangeKey, type ScopeRequest } from "../../utils/dashboardSummary";
import { filterTills, onlyTill, onlyTills, toggleTill } from "../../utils/tillSelection";

const RANGES: RangeKey[] = ["shift", "today", "week", "month", "custom"];

interface Props {
  request: ScopeRequest;
  availableProfiles: string[];
  onChange: (next: ScopeRequest) => void;
}

/**
 * The whole filter surface: which period, which tills. It replaces a drawer of four selects
 * that had to be opened before the reader could tell what they were looking at.
 */
export default function ScopeBar({ request, availableProfiles, onChange }: Props) {
  const [showTills, setShowTills] = useState(false);
  const [tillSearch, setTillSearch] = useState("");
  const tillMenu = useRef<HTMLDivElement>(null);
  const allTills = request.profiles.length === 0;
  const selectedCount = allTills ? availableProfiles.length : request.profiles.length;
  const shownTills = filterTills(availableProfiles, tillSearch);
  const setTills = (profiles: string[]) => onChange({ ...request, profiles });

  // Click outside or Escape closes the menu, and the search starts empty next time.
  useEffect(() => {
    if (!showTills) return;
    const close = () => {
      setShowTills(false);
      setTillSearch("");
    };
    const onMouseDown = (event: MouseEvent) => {
      if (!tillMenu.current?.contains(event.target as Node)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [showTills]);

  const tillLabel = allTills
    ? `All tills (${availableProfiles.length})`
    : request.profiles.length === 1
      ? request.profiles[0]
      : `${request.profiles.length} tills`;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap items-center gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        {RANGES.map((range) => (
          <button
            key={range}
            type="button"
            onClick={() => onChange({ ...request, range })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              request.range === range
                ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white"
                : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
            }`}
          >
            {RANGE_LABELS[range]}
          </button>
        ))}
      </div>

      {request.range === "custom" && (
        <div className="flex items-center gap-1 rounded-lg border border-gray-300 px-2 py-1 dark:border-gray-600">
          <Calendar className="h-4 w-4 text-gray-400" />
          <input
            type="date"
            value={request.dateFrom || ""}
            onChange={(event) => onChange({ ...request, dateFrom: event.target.value })}
            className="bg-transparent text-sm text-gray-900 outline-none dark:text-white"
          />
          <span className="text-gray-400">–</span>
          <input
            type="date"
            value={request.dateTo || ""}
            onChange={(event) => onChange({ ...request, dateTo: event.target.value })}
            className="bg-transparent text-sm text-gray-900 outline-none dark:text-white"
          />
        </div>
      )}

      {availableProfiles.length > 1 && (
        <div className="relative" ref={tillMenu}>
          <button
            type="button"
            onClick={() => setShowTills((open) => !open)}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            {tillLabel}
            <ChevronDown className="h-4 w-4" />
          </button>

          {showTills && (
            <div className="absolute right-0 z-20 mt-1 w-80 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
              <div className="border-b border-gray-100 p-2 dark:border-gray-700">
                <div className="flex items-center gap-2 rounded-md border border-gray-300 px-2 py-1.5 dark:border-gray-600">
                  <Search className="h-4 w-4 text-gray-400" />
                  <input
                    autoFocus
                    type="text"
                    value={tillSearch}
                    onChange={(event) => setTillSearch(event.target.value)}
                    placeholder="Search tills…"
                    className="w-full bg-transparent text-sm text-gray-900 outline-none dark:text-white"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className="text-gray-500 dark:text-gray-400">
                    {selectedCount} of {availableProfiles.length} selected
                  </span>
                  <div className="flex gap-3">
                    {tillSearch.trim() && shownTills.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setTills(onlyTills(availableProfiles, shownTills))}
                        className="font-medium text-beveren-600 hover:underline"
                      >
                        Only matching ({shownTills.length})
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={allTills}
                      onClick={() => setTills([])}
                      className="font-medium text-beveren-600 hover:underline disabled:text-gray-400 disabled:no-underline"
                    >
                      All tills
                    </button>
                  </div>
                </div>
              </div>

              <div className="max-h-80 overflow-y-auto py-1">
                {shownTills.length === 0 && (
                  <p className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">No till matches “{tillSearch.trim()}”</p>
                )}
                {shownTills.map((profile) => {
                  const selected = allTills || request.profiles.includes(profile);
                  // The last ticked till can't be unticked: no tills would read as all tills.
                  const locked = selected && selectedCount === 1;
                  return (
                    <div
                      key={profile}
                      className="group flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={locked}
                          onChange={() => setTills(toggleTill(request.profiles, availableProfiles, profile))}
                          className="h-4 w-4 rounded border-gray-300 text-beveren-600"
                        />
                        <span title={profile} className="truncate">{profile}</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setTills(onlyTill(availableProfiles, profile))}
                        className="rounded px-1.5 py-0.5 text-xs font-medium text-beveren-600 opacity-0 hover:bg-beveren-50 focus:opacity-100 group-hover:opacity-100 dark:hover:bg-gray-600"
                      >
                        Only
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
