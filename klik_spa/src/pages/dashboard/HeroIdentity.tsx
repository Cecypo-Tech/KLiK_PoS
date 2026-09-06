import { AlertTriangle } from "lucide-react";
import type { DashboardIdentity } from "../../utils/dashboardSummary";

interface Props {
  identity: DashboardIdentity;
  context: string[];
  formatMoney: (amount: number) => string;
}

/**
 * Billed, collected, credit — the three figures that answer "where is my money", and the one
 * line that ties them together. The old page led with revenue alone, which said nothing
 * about whether the money had actually arrived.
 */
export default function HeroIdentity({ identity, context, formatMoney }: Props) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 sm:p-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Figure label="Billed" value={formatMoney(identity.billed)} emphasis />
        <Figure
          label="Collected"
          value={formatMoney(identity.collected)}
          note={identity.collected_later ? `${formatMoney(identity.collected_later)} on account` : undefined}
        />
        <Figure
          label="Credit"
          value={formatMoney(identity.credit)}
          note={
            identity.credit_invoices
              ? `${identity.credit_invoices} invoice${identity.credit_invoices === 1 ? "" : "s"}, ${identity.credit_customers} customer${identity.credit_customers === 1 ? "" : "s"}`
              : undefined
          }
          tone={identity.credit ? "warn" : undefined}
        />
      </div>

      <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">{context.join(" · ")}</p>

      {identity.refunds_owed > 0 && (
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {formatMoney(identity.refunds_owed)} of refunds still owed to customers
        </p>
      )}

      {identity.unexplained !== 0 && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {formatMoney(identity.unexplained)} is unaccounted for. Billed should equal collected
            plus credit; a difference here is a data problem worth chasing, not a rounding
            artefact.
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
