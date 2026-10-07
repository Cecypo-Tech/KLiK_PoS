"use client";

import { useEffect, useRef, useState } from "react";
import { X, Zap } from "lucide-react";
import { toast } from "react-toastify";

import type { CartItem, MenuItem } from "../../types";
import { useCartStore } from "../stores/cartStore";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useProductStore } from "../stores/productStore";
import { useSalespersonStore } from "../stores/salespersonStore";
import { getCSRFToken } from "../utils/csrf";
import { isItemOutOfStock } from "../utils/stock";
import {
  MAX_LINES,
  problemsFirst,
  reviewOutcome,
  rowProblem,
  splitLines,
  toRows,
  withMatch,
  type ResolvedLine,
  type ReviewContext,
  type ReviewRow,
} from "../utils/quickEntry";

interface QuickEntryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** The till needs a salesperson signed in before anything goes into the cart. */
  onNeedSalesperson: () => void;
}

async function resolveLines(lines: string[], context: Record<string, string | undefined>): Promise<ResolvedLine[]> {
  const response = await fetch("/api/method/klik_pos.api.item.quick_entry.resolve_lines", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": getCSRFToken() ?? "" },
    body: JSON.stringify({ lines, ...context }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !Array.isArray(result.message)) {
    const messages = JSON.parse(result._server_messages || "[]").map((m: string) => JSON.parse(m).message);
    throw new Error(
      messages.join(" ").replace(/<[^>]*>/g, "") || `Could not match the items (server answered ${response.status})`
    );
  }
  return result.message;
}

export default function QuickEntryDialog({ isOpen, onClose, onNeedSalesperson }: QuickEntryDialogProps) {
  const [text, setText] = useState("");
  /** Set while the cashier reviews the lines; nothing is in the cart yet. */
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const posDetails = usePOSProfileStore((s) => s.posDetails);
  const warehouse = usePOSProfileStore((s) => s.warehouse);
  const isTaxIncludedInBasicRate =
    posDetails?.is_tax_included_in_basic_rate === 1
    || posDetails?.is_tax_included_in_basic_rate === "1"
    || posDetails?.is_tax_included_in_basic_rate === true;

  useEffect(() => {
    if (!isOpen) return;
    // Back to wherever the cashier was (the search box, usually) once the box closes.
    const returnFocusTo = document.activeElement as HTMLElement | null;
    setTimeout(() => textareaRef.current?.focus(), 0);
    return () => returnFocusTo?.focus?.();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        e.preventDefault();
        // Esc in the review goes back to the pasted text; in the text box it closes.
        if (rows) setRows(null);
        else onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose, busy, rows]);

  if (!isOpen) return null;

  const context = () => {
    const products = useProductStore.getState();
    return {
      customer: products.getEffectiveCustomer()?.id || undefined,
      price_list: products.getEffectivePriceList() || undefined,
      warehouse: warehouse || undefined,
    };
  };
  const reviewContext = (): ReviewContext => ({
    allowRateChange: !!posDetails?.allow_rate_change,
    isOutOfStock: (item) =>
      isItemOutOfStock(
        item as unknown as MenuItem,
        useProductStore.getState().stockUnavailable,
        !!posDetails?.custom_enable_loss_of_sale
      ),
  });

  /** Everything ready goes in at once; then the box closes. */
  const addRows = async (ready: ReviewRow[]) => {
    const outcome = reviewOutcome(ready, reviewContext());
    const cart = useCartStore.getState();
    const lineIds = await cart.addManyToCart(
      outcome.toAdd.map((entry) => ({
        item: { ...(entry.item as unknown as CartItem), item_code: String(entry.item.id) },
        qty: entry.qty,
      }))
    );
    // As the item list's '*' shortcut: a typed price is in the till's own tax terms.
    outcome.toAdd.forEach((entry, i) => {
      const lineId = lineIds[i];
      if (lineId && entry.rate !== null) cart.requestCustomRate(lineId, entry.rate, isTaxIncludedInBasicRate);
    });
    const added = lineIds.filter(Boolean).length;
    if (added) toast.success(`Added ${added} line${added === 1 ? "" : "s"} to the cart`);
    if (outcome.skipped.length) toast.info(`Skipped: ${outcome.skipped.map((r) => r.text).join("; ")}`);
    setRows(null);
    setText("");
    onClose();
  };

  const submit = async () => {
    const lines = splitLines(text);
    if (lines.length === 0 || busy) return;
    if (lines.length > MAX_LINES) {
      toast.error(`Enter at most ${MAX_LINES} lines at a time`);
      return;
    }
    // The product list's own gate: a till that needs a salesperson signed in first.
    if (posDetails?.custom_sales_person_pin_required) {
      const salespeople = useSalespersonStore.getState();
      await salespeople.ensureInitialized();
      if (!useSalespersonStore.getState().activeSalesperson) {
        onNeedSalesperson();
        return;
      }
    }
    setBusy(true);
    try {
      const answered = toRows(lines, await resolveLines(lines.map((l) => l.text), context()));
      const ctx = reviewContext();
      if (answered.every((row) => rowProblem(row, ctx) === null)) await addRows(answered);
      else setRows(problemsFirst(answered, ctx));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add the items");
    } finally {
      setBusy(false);
    }
  };

  const updateRow = (line: number, patch: Partial<ReviewRow>) =>
    setRows((current) => current && current.map((r) => (r.line === line ? { ...r, ...patch } : r)));

  /** Re-match one row from a picked candidate or a typed code; its qty and rate stay. */
  const rematch = async (line: number, query: string) => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const [match] = await resolveLines([query], context());
      if (match) setRows((current) => current && current.map((r) => (r.line === line ? withMatch(r, match) : r)));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not match the item");
    } finally {
      setBusy(false);
    }
  };

  const review = rows ? reviewOutcome(rows, reviewContext()) : null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" onClick={() => !busy && onClose()}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-entry-title"
        // Keys typed here are for the box: the POS's own shortcuts (F2, F3, F10...) listen on
        // the document and must not act behind it. Esc still closes it.
        onKeyDown={(e) => {
          if (e.key !== "Escape") e.stopPropagation();
        }}
        className={`relative z-10 ${rows ? "w-[960px]" : "w-[520px]"} max-w-[92vw] max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2.5">
            <Zap className="w-[18px] h-[18px] text-gray-500 dark:text-gray-400" />
            <span id="quick-entry-title" className="text-sm font-semibold text-gray-900 dark:text-white">
              Quick Entry
            </span>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {!rows && (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Paste the order as it came - codes, part numbers, barcodes, "5pcs", "x5", "@220" for a price. No
                quantity means 1.
              </p>
              <textarea
                id="quick-entry-text"
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    void submit();
                  }
                }}
                rows={8}
                spellCheck={false}
                disabled={busy}
                placeholder={"AP004 2\n5pcs 51360-TMJ-T01-B\nmimosa, 1, 220"}
                className="w-full px-3 py-2 font-mono text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-beveren-500"
              />
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-gray-400 dark:text-gray-500">Ctrl+Enter to add</span>
                <button
                  onClick={() => void submit()}
                  disabled={busy || !text.trim()}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-beveren-600 text-white hover:bg-beveren-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {busy ? "Adding…" : "Add to cart"}
                </button>
              </div>
            </>
          )}

          {rows && review && (
            <>
              <p className="text-xs text-gray-600 dark:text-gray-300">
                {review.blocked.length
                  ? `${review.blocked.length} line${review.blocked.length === 1 ? "" : "s"} need a look before anything is added.`
                  : "All lines ready."}
              </p>
              <div className="max-h-[55vh] overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                    <tr>
                      <th className="p-2 text-left">#</th>
                      <th className="p-2 text-left">Line</th>
                      <th className="p-2 text-left">Item</th>
                      <th className="p-2 w-20">Qty</th>
                      <th className="p-2">Rate</th>
                      <th className="p-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const problem = row.skip ? null : rowProblem(row, reviewContext());
                      return (
                        <tr
                          key={row.line}
                          className={`border-t border-gray-100 dark:border-gray-800 text-gray-800 dark:text-gray-200 ${
                            row.skip ? "opacity-40" : problem ? "bg-amber-50 dark:bg-amber-900/20" : ""
                          }`}
                        >
                          <td className="p-2 text-gray-400">{row.line}</td>
                          <td className="p-2 font-mono">{row.text}</td>
                          <td className="p-2">
                            {row.status === "ok" && row.item ? (
                              <span>
                                {String(row.item.id)} - {String(row.item.name)}
                              </span>
                            ) : (row.status === "many" || row.status === "conflict") && row.candidates.length > 0 ? (
                              <select
                                aria-label={`Item for line ${row.line}`}
                                disabled={busy}
                                defaultValue=""
                                onChange={(e) => void rematch(row.line, e.target.value)}
                                className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 p-1"
                              >
                                <option value="" disabled>
                                  Pick the item…
                                </option>
                                {row.candidates.map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.code} - {c.name}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                aria-label={`Item code for line ${row.line}`}
                                disabled={busy}
                                placeholder="Type the item code, Enter"
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    void rematch(row.line, e.currentTarget.value);
                                  }
                                }}
                                className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 p-1 font-mono"
                              />
                            )}
                            {problem && <div className="mt-0.5 text-amber-700 dark:text-amber-300">{problem}</div>}
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              min="0"
                              step="any"
                              aria-label={`Quantity for line ${row.line}`}
                              value={row.qty}
                              disabled={busy}
                              onChange={(e) => updateRow(row.line, { qty: Number(e.target.value), qty_ambiguous: false })}
                              // Looking at a flagged quantity and leaving it is confirming it.
                              onBlur={() => row.qty_ambiguous && updateRow(row.line, { qty_ambiguous: false })}
                              className={`w-16 rounded border p-1 text-right bg-white dark:bg-gray-800 ${
                                row.qty_ambiguous
                                  ? "border-amber-500 ring-1 ring-amber-400"
                                  : "border-gray-300 dark:border-gray-600"
                              }`}
                            />
                          </td>
                          <td className="p-2 text-right whitespace-nowrap">
                            {row.rate !== null && (
                              <>
                                {row.rate}
                                <button
                                  aria-label="Use the till's price"
                                  disabled={busy}
                                  onClick={() => updateRow(row.line, { rate: null })}
                                  className="ml-1 text-gray-400 hover:text-gray-600"
                                >
                                  <X size={12} className="inline" />
                                </button>
                              </>
                            )}
                          </td>
                          <td className="p-2 text-right">
                            <button
                              disabled={busy}
                              onClick={() => updateRow(row.line, { skip: !row.skip })}
                              className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 underline"
                            >
                              {row.skip ? "Keep" : "Skip"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between">
                <button
                  disabled={busy}
                  onClick={() => setRows(null)}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200"
                >
                  Back
                </button>
                <button
                  disabled={busy || review.blocked.length > 0 || review.toAdd.length === 0}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await addRows(rows);
                    } finally {
                      setBusy(false);
                    }
                  }}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-beveren-600 text-white hover:bg-beveren-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {busy ? "Adding…" : `Add ${review.toAdd.length} to cart`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
