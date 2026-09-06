import { useState } from "react";
import { Calendar, Check, ChevronDown } from "lucide-react";
import { RANGE_LABELS, type RangeKey, type ScopeRequest } from "../../utils/dashboardSummary";

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
  const allTills = request.profiles.length === 0;

  const toggleTill = (profile: string) => {
    const selected = allTills ? [...availableProfiles] : [...request.profiles];
    const next = selected.includes(profile)
      ? selected.filter((name) => name !== profile)
      : [...selected, profile];
    // Everything selected means the same thing as no filter, and says so in the label.
    onChange({ ...request, profiles: next.length === availableProfiles.length ? [] : next });
  };

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
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowTills((open) => !open)}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            {tillLabel}
            <ChevronDown className="h-4 w-4" />
          </button>

          {showTills && (
            <div className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800">
              <button
                type="button"
                onClick={() => onChange({ ...request, profiles: [] })}
                className="flex w-full items-center justify-between px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                All tills
                {allTills && <Check className="h-4 w-4 text-beveren-600" />}
              </button>
              {availableProfiles.map((profile) => {
                const selected = allTills || request.profiles.includes(profile);
                return (
                  <button
                    key={profile}
                    type="button"
                    onClick={() => toggleTill(profile)}
                    className="flex w-full items-center justify-between px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    <span className="truncate">{profile}</span>
                    {selected && <Check className="h-4 w-4 text-beveren-600" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
