import { Loader2, Search } from "lucide-react";
import type { MpesaRegisterPayment } from "../../services/mpesa";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import { receiptCardState } from "../../utils/mpesaReceipts";
import { canSendStk } from "../../utils/stkAutoSubmit";

interface MpesaOptionsModalProps {
  isOpen: boolean;
  modeOfPayment: string;
  amount: number;
  phoneNumber: string;
  currencySymbol: string;
  searchTerm: string;
  payments: MpesaRegisterPayment[];
  pendingCount: number;
  selectedPaymentNames: string[];
  selectedTotal: number;
  isLoadingPayments: boolean;
  isProcessing: boolean;
  /** A push for this sale is waiting on the customer: another would ring them twice. */
  stkPending?: boolean;
  /** A push for this sale was paid: submit it, don't ask the customer again. */
  stkPaid?: boolean;
  onClose: () => void;
  onPhoneNumberChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onTogglePayment: (paymentName: string) => void;
  onInitiateStk: () => void;
  onAddPayments: () => void;
  /** "modal" keeps the overlay (mobile). "panel" renders inline for the full-screen desktop checkout. */
  variant?: "modal" | "panel";
}

export default function MpesaOptionsModal({
  isOpen,
  modeOfPayment,
  amount,
  phoneNumber,
  currencySymbol,
  searchTerm,
  payments,
  pendingCount,
  selectedPaymentNames,
  selectedTotal,
  isLoadingPayments,
  isProcessing,
  stkPending = false,
  stkPaid = false,
  onClose,
  onPhoneNumberChange,
  onSearchChange,
  onTogglePayment,
  onInitiateStk,
  onAddPayments,
  variant = "modal",
}: MpesaOptionsModalProps) {
  if (!isOpen) return null;

  const stkSendable = canSendStk({ isProcessing, stkPending, stkPaid });

  return (
    <div className={variant === "panel"
      ? "w-full"
      : "fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4"}>
      <div className={variant === "panel"
        ? "w-full rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 overflow-hidden"
        : "w-full max-w-3xl rounded-2xl bg-white dark:bg-gray-900 shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden"}>

        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">M-Pesa Payment Options</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {modeOfPayment} • Expected amount {formatCurrencyWithSymbol(amount, currencySymbol)}
            </p>
          </div>
          {variant !== "panel" && (
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Close
          </button>
          )}
        </div>

        <div className={`grid md:grid-cols-5 ${variant === "panel" ? "gap-4 p-4" : "gap-6 p-6"}`}>
          <section className="md:col-span-2 space-y-4 rounded-xl border border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-900 p-4">
            <h3 className="font-semibold text-emerald-800 dark:text-emerald-300">Initiate STK Push</h3>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Phone Number</label>
              <input
                type="text"
                value={phoneNumber}
                onChange={(event) => onPhoneNumberChange(event.target.value)}
                onKeyDown={(event) => {
                  // Enter sends the push, exactly like the button.
                  if (event.key !== "Enter") return;
                  event.preventDefault();
                  if (stkSendable) onInitiateStk();
                }}
                placeholder="0712345678 or 254712345678"
                disabled={isProcessing}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-gray-900 dark:text-white"
              />
            </div>
            <button
              type="button"
              onClick={onInitiateStk}
              disabled={!stkSendable}
              className="w-full rounded-lg bg-emerald-600 px-4 py-3 font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isProcessing ? <Loader2 size={16} className="animate-spin" /> : null}
              <span>{stkPaid ? "Paid — submit the sale" : stkPending ? "Waiting on the customer…" : "Send STK Push"}</span>
            </button>
          </section>

          <section className="md:col-span-3 space-y-4 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-start justify-between gap-2 flex-wrap">
              <h3 className="font-semibold text-gray-900 dark:text-white">Reconcile Received C2B Payments</h3>
              <div className="flex flex-wrap gap-1.5">
                <span className="rounded-full border border-gray-300 dark:border-gray-600 px-2.5 py-0.5 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
                  {pendingCount} with money left
                </span>
                <span className="rounded-full border border-gray-300 dark:border-gray-600 px-2.5 py-0.5 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
                  Sender · Transaction ID · Reference
                </span>
              </div>
            </div>

            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder="Type at least 3 characters"
                disabled={isProcessing}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 pl-9 pr-3 py-2 text-gray-900 dark:text-white"
              />
            </div>

            {/* Nothing below the box until a search runs: its placeholder already says how. */}
            {(isLoadingPayments || searchTerm.trim().length >= 3) && (
            <div className="max-h-60 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
              {isLoadingPayments ? (
                <div className="p-4 text-sm text-gray-500 dark:text-gray-400 flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Loading M-Pesa payments...</span>
                </div>
              ) : payments.length === 0 ? (
                <div className="p-4 text-sm text-gray-500 dark:text-gray-400">
                  No pending payments matched your search.
                </div>
              ) : (
                payments.map((payment) => {
                  const checked = selectedPaymentNames.includes(payment.name);
                  const card = receiptCardState(payment);
                  return (
                    <label
                      key={payment.name}
                      className={`flex items-start gap-3 p-3 ${card.selectable ? "cursor-pointer" : "cursor-not-allowed opacity-60"} ${checked ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-white dark:bg-gray-900"}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onTogglePayment(payment.name)}
                        disabled={isProcessing || !card.selectable}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium text-gray-900 dark:text-white truncate">
                            {payment.full_name || payment.name}
                          </span>
                          <span className="text-right whitespace-nowrap">
                            <span className={`block font-semibold ${card.selectable ? "text-emerald-700 dark:text-emerald-400" : "text-gray-400"}`}>
                              {formatCurrencyWithSymbol(card.openAmount, currencySymbol)}
                              {card.kind !== "new" ? " left" : ""}
                            </span>
                            {card.kind !== "new" && (
                              <span className="block text-xs text-gray-500 dark:text-gray-400">
                                of {formatCurrencyWithSymbol(card.total, currencySymbol)}
                                {card.usedCount > 0 ? ` · used on ${card.usedCount} sale${card.usedCount === 1 ? "" : "s"}` : ""}
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                          <div>
                            {payment.transid || payment.name}
                            {payment.msisdn ? ` - ${payment.msisdn}` : ""}
                          </div>
                          <div>{payment.billrefnumber || "No reference"}</div>
                          {card.kind === "other" && (
                            <div className="text-amber-600 dark:text-amber-400">
                              Held by {card.heldBy}. Switch customer to use it.
                            </div>
                          )}
                        </div>
                      </div>
                    </label>
                  );
                })
              )}
            </div>
            )}

            <div className="flex items-center justify-between rounded-lg bg-gray-50 dark:bg-gray-800 px-4 py-3 text-sm">
              <span className="text-gray-600 dark:text-gray-300">Selected total</span>
              <span className="font-semibold text-gray-900 dark:text-white">
                {formatCurrencyWithSymbol(selectedTotal, currencySymbol)}
              </span>
            </div>

            <button
              type="button"
              onClick={onAddPayments}
              disabled={isProcessing || stkPending || stkPaid || selectedPaymentNames.length === 0}
              className="w-full rounded-lg bg-blue-600 px-4 py-3 font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isProcessing ? <Loader2 size={16} className="animate-spin" /> : null}
              <span>Add Selected Payments</span>
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}