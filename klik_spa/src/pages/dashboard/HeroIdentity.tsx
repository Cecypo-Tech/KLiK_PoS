import { AlertTriangle } from "lucide-react";
import type { DashboardIdentity } from "../../utils/dashboardSummary";

interface Props {
  identity: DashboardIdentity;
  context: string[];
  formatMoney: (amount: number) => string;
}

/**
 * Billed, credited, collected, balance — the four figures that answer "where is my money",
 * and they subtract left to right. A return follows the sale it is against, so a credit
 * note issued days later still shows here, against the sale it reduced.
 */
export default function HeroIdentity({ identity, context, formatMoney }: Props) {
  const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;
  const creditedNote = [
    identity.credited_notes ? plural(identity.credited_notes, "credit note") : "",
    identity.credited_outside ? `${formatMoney(identity.credited_outside)} issued outside this period` : "",
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 sm:p-5">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Figure label="Billed" value={formatMoney(identity.billed)} emphasis />
        <Figure label="Credited" value={formatMoney(identity.credited)} note={creditedNote || undefined} />
        <Figure
          label="Collected"
          value={formatMoney(identity.collected)}
          note={identity.collected_later ? `${formatMoney(identity.collected_later)} on account` : undefined}
        />
        <Figure
          label="Balance"
          value={formatMoney(identity.credit)}
          note={
            identity.credit_invoices
              ? `${plural(identity.credit_invoices, "invoice")}, ${plural(identity.credit_customers, "customer")}`
              : undefined
          }
          tone={identity.credit ? "warn" : undefined}
        />
      </div>

      <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">{context.join(" · ")}</p>

      {identity.returned_earlier?.count > 0 && (
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {`${formatMoney(identity.returned_earlier.amount)} returned in this period against earlier sales (${plural(identity.returned_earlier.count, "credit note")}), counted with those sales`}
        </p>
      )}

      {identity.write_off !== 0 && (
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {formatMoney(identity.write_off)} written off
        </p>
      )}

      {identity.refunds_owed > 0 && (
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {formatMoney(identity.refunds_owed)} of refunds still owed to customers
        </p>
      )}

      {identity.outside_tills && identity.outside_tills.invoices > 0 && (
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {`${formatMoney(identity.outside_tills.amount)} more billed off these tills (${plural(identity.outside_tills.invoices, "invoice")}), not counted here`}
        </p>
      )}

      {identity.unexplained !== 0 && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {formatMoney(identity.unexplained)} does not add up. Billed less credited and
            collected should equal the balance; the difference was settled another way, such
            as a journal entry or a reconciliation, and is worth checking.
          </span>
        </p>
      )}
    </section>
  );
}

function Figure({
  label,
  value,
  note,
  emphasis,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: boolean;
  tone?: "warn";
}) {
  return (
    <div>
      <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
      <p
        className={`font-bold tracking-tight ${emphasis ? "text-2xl sm:text-3xl" : "text-xl sm:text-2xl"} ${
          tone === "warn" ? "text-amber-600 dark:text-amber-400" : "text-gray-900 dark:text-white"
        }`}
      >
        {value}
      </p>
      {note && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{note}</p>}
    </div>
  );
}
