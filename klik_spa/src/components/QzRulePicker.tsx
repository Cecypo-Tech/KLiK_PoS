import { useEffect, useState } from "react";
import type { QzRuleOption } from "../utils/qzPrint";

interface QzRulePickerProps {
  open: boolean;
  options: QzRuleOption[];
  onConfirm: (rules: string[]) => void;
  onCancel: () => void;
}

const ticked = (options: QzRuleOption[]) => options.filter((o) => !o.limit_reached).map((o) => o.rule);

/**
 * Which rules to print via QZ, when more than one matches: all ticked except
 * those at their print limit (the desk sidebar's checklist). Untick what isn't
 * needed this time — a second packing list, an invoice the customer already has.
 */
export default function QzRulePicker({ open, options, onConfirm, onCancel }: QzRulePickerProps) {
  const [chosen, setChosen] = useState<string[]>(() => ticked(options));
  useEffect(() => {
    if (open) setChosen(ticked(options));
  }, [open, options]);

  if (!open) return null;

  const toggle = (rule: string) =>
    setChosen((c) => (c.includes(rule) ? c.filter((r) => r !== rule) : [...c, rule]));

  return (
    // Above PaymentDialog's full-screen layer (z-[60] on desktop).
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-label="Print via QZ"
        className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl dark:bg-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">Print via QZ</h3>
        <div className="space-y-2">
          {options.map((o) => (
            <label key={o.rule} className="flex items-center gap-3 text-sm text-gray-800 dark:text-gray-200">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={chosen.includes(o.rule)}
                onChange={() => toggle(o.rule)}
              />
              <span>{o.limit_reached ? `${o.rule} (limit reached)` : o.rule}</span>
            </label>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg bg-beveren-600 px-4 py-2 text-sm font-medium text-white hover:bg-beveren-700 disabled:opacity-50"
            disabled={!chosen.length}
            onClick={() => onConfirm(options.map((o) => o.rule).filter((r) => chosen.includes(r)))}
          >
            Print
          </button>
        </div>
      </div>
    </div>
  );
}
