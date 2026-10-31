import { useCallback, useEffect, useState } from "react";
import { toast } from "react-toastify";
import BottomNavigation from "../components/BottomNavigation";
import QzPrintIcon from "../components/QzPrintIcon";
import QzRulePicker from "../components/QzRulePicker";
import { useQzPrint } from "../hooks/useQzPrint";
import { getExpenseTypes, getShiftExpenses, recordExpense, type ShiftExpense } from "../services/expense";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { getCSRFToken } from "../utils/csrf";

const input = "w-full rounded-lg border border-gray-300 bg-white px-3 py-3 text-base dark:border-gray-600 dark:bg-gray-800 dark:text-white";

export function ExpenseForm({ types, saving, onSave }: {
  types: { label: string }[];
  saving: boolean;
  /** Resolves true when saved, so the form clears. */
  onSave: (label: string, amount: number, note: string) => Promise<boolean>;
}) {
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const value = Number(amount);
  const canSave = !saving && !!label && value > 0;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSave) return;
    if (await onSave(label, value, note.trim())) {
      setLabel("");
      setAmount("");
      setNote("");
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <select name="label" value={label} onChange={(e) => setLabel(e.target.value)} className={input} aria-label="Expense type">
        <option value="">Select a type</option>
        {types.map((t) => <option key={t.label} value={t.label}>{t.label}</option>)}
      </select>
      <input name="amount" inputMode="decimal" placeholder="Amount" value={amount}
        onChange={(e) => setAmount(e.target.value)} className={input} aria-label="Amount" />
      <input name="note" placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)}
        className={input} aria-label="Note" />
      <button type="submit" disabled={!canSave}
        className="w-full rounded-lg bg-beveren-600 py-3 font-medium text-white disabled:opacity-50">Save</button>
    </form>
  );
}

function RowQzButton({ name }: { name: string }) {
  const qz = useQzPrint(name, false, false, "Journal Entry");
  return (
    <>
      <button type="button" title="QZ Print" aria-label="QZ Print" className="p-1" onClick={qz.start} disabled={qz.busy}>
        <QzPrintIcon size={16} />
      </button>
      <QzRulePicker {...qz.picker} />
    </>
  );
}

export function ExpenseList({ rows, qz, currency = "" }: { rows: ShiftExpense[]; qz: boolean; currency?: string }) {
  if (!rows.length) return <p className="text-sm text-gray-500">No expenses yet this shift.</p>;
  return (
    <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white dark:divide-gray-700 dark:border-gray-700 dark:bg-gray-800">
      {rows.map((r) => (
        <li key={r.name} className="flex items-center justify-between gap-3 p-3">
          <div className="min-w-0">
            <div className="font-medium text-gray-900 dark:text-white">{r.label}</div>
            {r.note && <div className="truncate text-sm text-gray-500">{r.note}</div>}
            <div className="text-xs text-gray-400">{r.owner} · {r.creation.slice(11, 16)}</div>
            {r.docstatus === 0 && <span className="text-xs font-medium text-amber-600">Awaiting approval</span>}
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold">{currency} {Number(r.amount).toFixed(2)}</span>
            {qz && <RowQzButton name={r.name} />}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Records an expense, then refreshes the list on success AND failure: a lost response may still have committed. */
export async function submitExpense(label: string, amount: number, note: string, refresh: () => Promise<void> | void) {
  const res = await recordExpense(label, amount, note, getCSRFToken() ?? "");
  void refresh();
  return res;
}

export default function ExpensesPage() {
  const { posDetails } = usePOSProfileStore();
  const [types, setTypes] = useState<{ label: string }[]>([]);
  const [rows, setRows] = useState<ShiftExpense[]>([]);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => setRows(await getShiftExpenses()), []);
  useEffect(() => {
    void getExpenseTypes().then(setTypes);
    void refresh();
  }, [refresh]);

  const save = async (label: string, amount: number, note: string) => {
    setSaving(true);
    const res = await submitExpense(label, amount, note, refresh);
    setSaving(false);
    if (!res.ok) {
      toast.error(res.error);
      return false;
    }
    toast.success(res.docstatus === 0 ? "Expense saved, awaiting approval" : "Expense saved");
    return true;
  };

  const qz = [1, "1", true].includes(posDetails?.custom_enable_qz_print as 1 | "1" | true);
  return (
    <div className="min-h-screen bg-gray-50 pb-20 dark:bg-gray-900 lg:ml-20 lg:pb-2">
      <div className="mx-auto max-w-xl space-y-6 p-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Expenses</h1>
        <ExpenseForm types={types} saving={saving} onSave={save} />
        <ExpenseList rows={rows} qz={qz} currency={posDetails?.currency_symbol ?? posDetails?.currency ?? ""} />
      </div>
      <BottomNavigation />
    </div>
  );
}
