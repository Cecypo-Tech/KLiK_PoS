import { useState } from "react";
import type { KeyboardEvent } from "react";
import { Loader2, Search, X } from "lucide-react";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import type { CustomerCredit } from "../../utils/customerCredit";
import {
  appliedTotal,
  isUsable,
  voucherCustomerRule,
  voucherStatusLabel,
  type AppliedVoucher,
  type VoucherLookup,
} from "../../utils/voucher";

interface VoucherPanelProps {
  isOpen: boolean;
  currencySymbol: string;
  /** The sale's customer, for the voucher's customer rule. */
  saleCustomer: { customer: string; isWalkin: boolean };
  /** A named customer's own open credit - never a Walk In's. */
  ownCredit: CustomerCredit | null;
  applied: AppliedVoucher[];
  disabled: boolean;
  onLookup: (creditNote: string, originalInvoice: string) => Promise<VoucherLookup>;
  onApply: (voucher: { note: string; original: string | null; available: number }) => void;
  onRemove: (note: string) => void;
  /** Spend part of an applied voucher - the dialog caps it at the balance and the sale. */
  onResize: (note: string, amount: number) => void;
  onSwitchCustomer: (customer: string) => void;
  onClose: () => void;
}

/** Store-credit vouchers: a credit note's number plus its original sale's, both on the
return receipt. Shaped like the M-Pesa panel. */
export default function VoucherPanel({
  isOpen,
  currencySymbol,
  saleCustomer,
  ownCredit,
  applied,
  disabled,
  onLookup,
  onApply,
  onRemove,
  onResize,
  onSwitchCustomer,
  onClose,
}: VoucherPanelProps) {
  const [creditNote, setCreditNote] = useState("");
  const [originalInvoice, setOriginalInvoice] = useState("");
  const [lookup, setLookup] = useState<VoucherLookup | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  if (!isOpen) return null;

  const money = (value: number) => formatCurrencyWithSymbol(value, currencySymbol);
  const appliedNotes = new Set(applied.map((voucher) => voucher.note));
  const ownNotes = ownCredit?.notes ?? [];
  const inputClass =
    "w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-gray-900 dark:text-white";

  const check = async () => {
    if (checking || !creditNote.trim() || !originalInvoice.trim()) return;
    setChecking(true);
    setLookupError(null);
    try {
      setLookup(await onLookup(creditNote.trim(), originalInvoice.trim()));
    } catch (error) {
      setLookup(null);
      setLookupError(error instanceof Error ? error.message : "Could not check the voucher.");
    } finally {
      setChecking(false);
    }
  };

  const checkOnEnter = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    void check();
  };

  const rule =
    lookup && isUsable(lookup) && lookup.customer
      ? voucherCustomerRule(saleCustomer, { customer: lookup.customer, isWalkin: Boolean(lookup.is_walkin) })
      : null;
  const owner = lookup?.customer_name || lookup?.customer || "";

  return (
    <div className="w-full rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Vouchers (store credit)</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Credit note number and original sale number, both from the return receipt.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {applied.length > 0 && (
            <span className="rounded-full border border-gray-300 dark:border-gray-600 px-2.5 py-0.5 text-xs text-gray-700 dark:text-gray-200 whitespace-nowrap">
              Applied {money(appliedTotal(applied))}
            </span>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close vouchers"
            className="rounded-full p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-5 gap-4 p-4">
        <section className="md:col-span-3 space-y-3 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              aria-label="Credit note number"
              placeholder="Credit note no."
              value={creditNote}
              onChange={(event) => setCreditNote(event.target.value)}
              onKeyDown={checkOnEnter}
              disabled={disabled}
              className={inputClass}
            />
            <input
              aria-label="Original sale number"
              placeholder="Original sale no."
              value={originalInvoice}
              onChange={(event) => setOriginalInvoice(event.target.value)}
              onKeyDown={checkOnEnter}
              disabled={disabled}
              className={inputClass}
            />
          </div>
          <button
            type="button"
            onClick={() => void check()}
            disabled={disabled || checking || !creditNote.trim() || !originalInvoice.trim()}
            className="w-full rounded-lg bg-gray-800 dark:bg-gray-700 px-4 py-2 font-medium text-white hover:bg-gray-900 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {checking ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            <span>Check voucher</span>
          </button>

          {lookupError && <p className="text-sm text-red-600 dark:text-red-400">{lookupError}</p>}
          {lookup && (
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 space-y-2 text-sm">
              <div className="font-medium text-gray-900 dark:text-white">{voucherStatusLabel(lookup, money)}</div>
              {lookup.note && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {lookup.note} · sale {lookup.original} · {owner}
                  {lookup.walkin_name || lookup.walkin_phone
                    ? ` · ${[lookup.walkin_name, lookup.walkin_phone].filter(Boolean).join(", ")}`
                    : ""}
                </div>
              )}
              {rule === "apply" && lookup.note && (
                <button
                  type="button"
                  disabled={disabled || appliedNotes.has(lookup.note)}
                  onClick={() =>
                    onApply({ note: lookup.note as string, original: lookup.original ?? null, available: lookup.available ?? 0 })
                  }
                  className="rounded-lg bg-beveren-600 px-3 py-1.5 text-white hover:bg-beveren-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  {appliedNotes.has(lookup.note) ? "Applied" : "Apply"}
                </button>
              )}
              {rule === "switch" && lookup.customer && (
                <div className="space-y-1">
                  <p className="text-gray-700 dark:text-gray-300">This voucher belongs to {owner}.</p>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onSwitchCustomer(lookup.customer as string)}
                    className="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-gray-800 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    Switch sale to {owner}
                  </button>
                </div>
              )}
              {rule === "refuse_named" && (
                <p className="text-amber-700 dark:text-amber-400">This voucher belongs to {owner}.</p>
              )}
              {rule === "refuse_walkin" && (
                <p className="text-amber-700 dark:text-amber-400">Walk In vouchers pay Walk In sales only.</p>
              )}
            </div>
          )}
        </section>

        <section className="md:col-span-2 space-y-3 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          {ownNotes.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">This customer's credit</h3>
              {ownNotes.map((note) => (
                <div key={note.invoice} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-gray-700 dark:text-gray-300">{note.invoice}</span>
                  <span className="whitespace-nowrap font-medium text-gray-900 dark:text-white">{money(note.available)}</span>
                  <button
                    type="button"
                    disabled={disabled || appliedNotes.has(note.invoice)}
                    onClick={() => onApply({ note: note.invoice, original: null, available: note.available })}
                    className="rounded-lg border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {appliedNotes.has(note.invoice) ? "Applied" : "Apply"}
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Applied to this sale</h3>
            {applied.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">None yet.</p>
            ) : (
              applied.map((voucher) => (
                <div key={voucher.note} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-gray-700 dark:text-gray-300">{voucher.note}</span>
                  {/* Keyed on the amount so a capped value shows once the dialog settles it. */}
                  <input
                    key={`${voucher.note}-${voucher.amount}`}
                    type="number"
                    min={0}
                    step="0.01"
                    defaultValue={voucher.amount}
                    disabled={disabled}
                    aria-label={`Amount from ${voucher.note}`}
                    onBlur={(event) => {
                      const value = Number(event.currentTarget.value);
                      // Show the held amount until the dialog settles: a value capped back to
                      // the same amount keeps the key, so nothing else would undo the typing.
                      event.currentTarget.value = String(voucher.amount);
                      if (Number.isFinite(value) && value !== voucher.amount) onResize(voucher.note, value);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") event.currentTarget.blur();
                    }}
                    className="w-28 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-right font-medium text-gray-900 dark:text-white disabled:opacity-50"
                  />
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onRemove(voucher.note)}
                    aria-label={`Remove ${voucher.note}`}
                    className="rounded-full p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
