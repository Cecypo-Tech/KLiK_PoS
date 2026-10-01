"use client";

import { useEffect, useRef, useState } from "react";
import { X, Zap } from "lucide-react";
import { toast } from "react-toastify";

import type { CartItem } from "../../types";
import { useCartStore } from "../stores/cartStore";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useProductStore } from "../stores/productStore";
import { getCSRFToken } from "../utils/csrf";
import { parseQuickEntry, planQuickEntry, type MatchResult, type QuickEntryPlan } from "../utils/quickEntry";

interface QuickEntryDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

async function matchItems(queries: string[], context: Record<string, string | undefined>): Promise<MatchResult[]> {
  const response = await fetch("/api/method/klik_pos.api.item.quick_entry.match_items", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": getCSRFToken() ?? "" },
    body: JSON.stringify({ queries, ...context }),
  });
  const result = await response.json();
  if (!response.ok || !Array.isArray(result.message)) {
    const messages = JSON.parse(result._server_messages || "[]").map((m: string) => JSON.parse(m).message);
    throw new Error(messages.join(" ").replace(/<[^>]*>/g, "") || "Could not match the items");
  }
  return result.message;
}

const qtyOf = (code: string) =>
  useCartStore
    .getState()
    .cartItems.filter((ci) => (ci.item_code || ci.id) === code)
    .reduce((sum, ci) => sum + ci.quantity, 0);

export default function QuickEntryDialog({ isOpen, onClose }: QuickEntryDialogProps) {
  const [text, setText] = useState("");
  const [failed, setFailed] = useState<QuickEntryPlan["failed"]>([]);
  const [busy, setBusy] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const posDetails = usePOSProfileStore((s) => s.posDetails);
  const warehouse = usePOSProfileStore((s) => s.warehouse);

  useEffect(() => {
    if (!isOpen) return;
    setTimeout(() => textareaRef.current?.focus(), 0);
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose, busy]);

  if (!isOpen) return null;

  const submit = async () => {
    const lines = parseQuickEntry(text);
    if (lines.length === 0 || busy) return;
    setBusy(true);
    try {
      const products = useProductStore.getState();
      const queries = lines.filter((l) => !l.error).map((l) => l.query);
      const results = queries.length
        ? await matchItems(queries, {
            customer: products.getEffectiveCustomer()?.id || undefined,
            price_list: products.getEffectivePriceList() || undefined,
            warehouse: warehouse || undefined,
          })
        : [];
      const plan = planQuickEntry(lines, results, { allowRateChange: !!posDetails?.allow_rate_change });

      const cart = useCartStore.getState();
      let added = 0;
      for (const entry of plan.toAdd) {
        const code = String(entry.item.id);
        const before = qtyOf(code);
        // One at a time: each add reads the cart the previous one left.
        await cart.addToCartWithQuantity({ ...(entry.item as unknown as CartItem), item_code: code }, entry.qty);
        if (qtyOf(code) === before) {
          // The cart refused it (not enough stock) and said why in its own toast.
          plan.failed.push({ line: entry.line, text: lines.find((l) => l.line === entry.line)?.text ?? code, reason: "Not added: see the message above" });
          continue;
        }
        added += 1;
        if (entry.rate !== null) {
          const lineInCart = useCartStore.getState().cartItems.find((ci) => (ci.item_code || ci.id) === code);
          if (lineInCart) cart.requestCustomRate(lineInCart.id, entry.rate);
        }
      }

      plan.failed.sort((a, b) => a.line - b.line);
      setFailed(plan.failed);
      setText(plan.failed.map((f) => f.text).join("\n"));
      if (added) toast.success(`Added ${added} line${added === 1 ? "" : "s"} to the cart`);
      if (plan.failed.length === 0) onClose();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add the items");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" onClick={() => !busy && onClose()}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-entry-title"
        className="relative z-10 w-[520px] max-w-[92vw] max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700"
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
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Enter <span className="font-semibold text-gray-700 dark:text-gray-200">item*, qty*, rate</span> - one
            per line. Part of the item code is enough when only one item matches; leave the rate out for the till's
            price.
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
            placeholder={"mimosa, 1\ntwist300, 5, 220"}
            className="w-full px-3 py-2 font-mono text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-beveren-500"
          />
          {failed.length > 0 && (
            <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-3 py-2">
              <p className="text-xs font-semibold text-red-700 dark:text-red-300 mb-1">
                {failed.length} line{failed.length === 1 ? "" : "s"} not added - fix and add again:
              </p>
              <ul className="space-y-0.5">
                {failed.map((f) => (
                  <li key={`${f.line}-${f.text}`} className="text-xs text-red-700 dark:text-red-300">
                    <span className="font-mono">{f.text}</span> - {f.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
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
        </div>
      </div>
    </div>
  );
}
