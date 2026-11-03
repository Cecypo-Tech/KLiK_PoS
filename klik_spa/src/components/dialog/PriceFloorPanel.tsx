import { useEffect, useState } from "react";
import { Loader2, ShieldAlert, ShieldCheck, X } from "lucide-react";

import { authorisePriceFloor, getSupervisors, type Supervisor } from "../../services/priceFloor";
import {
  authorisationStillValid,
  floorRowsKey,
  type FloorAuthorisation,
  type PriceFloor,
} from "../../utils/priceFloor";

interface Props {
  floor: PriceFloor | null;
  authorisation: FloorAuthorisation | null;
  /** The payload the preview was built from: the supervisor authorises exactly that cart. */
  getPreviewPayload: () => object | null;
  formatMoney: (value: number) => string;
  onAuthorised: (auth: FloorAuthorisation) => void;
  onFixPrices: () => void;
  /** Hold the sale and send it to a manager to approve remotely. Absent: no button. */
  onAskManager?: () => void;
  disabled?: boolean;
}

/** Lines below their price list's minimum, and the supervisor's way through. */
export default function PriceFloorPanel({
  floor,
  authorisation,
  getPreviewPayload,
  formatMoney,
  onAuthorised,
  onFixPrices,
  onAskManager,
  disabled,
}: Props) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const rows = floor?.rows ?? [];
  if (!rows.length) return null;

  if (authorisationStillValid(authorisation, rows)) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-green-300 bg-green-50 p-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
        <ShieldCheck className="h-4 w-4 shrink-0" />
        <span>Prices below the minimum authorised by {authorisation?.supervisorName || "a supervisor"}</span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
      <p className="flex items-center gap-2 font-semibold">
        <ShieldAlert className="h-4 w-4 shrink-0" />
        Below the minimum selling price
      </p>
      <ul className="mt-2 space-y-1">
        {rows.map((row) => (
          <li key={`${row.idx}-${row.item_code}`}>
            Row {row.idx} ({row.item_name}): {formatMoney(row.rate)} - minimum {formatMoney(row.minimum)}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onFixPrices}
          disabled={disabled}
          className="flex-1 rounded-lg border border-red-400 px-3 py-2 font-medium hover:bg-red-100 disabled:opacity-50 dark:hover:bg-red-900/30"
        >
          Fix prices
        </button>
        {onAskManager && (
          <button
            type="button"
            onClick={onAskManager}
            disabled={disabled}
            className="flex-1 rounded-lg border border-red-400 px-3 py-2 font-medium hover:bg-red-100 disabled:opacity-50 dark:hover:bg-red-900/30"
          >
            Ask manager
          </button>
        )}
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          disabled={disabled}
          className="flex-1 rounded-lg bg-red-600 px-3 py-2 font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          Authorise
        </button>
      </div>
      {dialogOpen && (
        <SupervisorAuthoriseDialog
          onClose={() => setDialogOpen(false)}
          onAuthorised={(token, supervisorName) => {
            setDialogOpen(false);
            onAuthorised({ token, key: floorRowsKey(rows), supervisorName });
          }}
          getPreviewPayload={getPreviewPayload}
        />
      )}
    </div>
  );
}

function SupervisorAuthoriseDialog({
  onClose,
  onAuthorised,
  getPreviewPayload,
}: {
  onClose: () => void;
  onAuthorised: (token: string, supervisorName: string) => void;
  getPreviewPayload: () => object | null;
}) {
  const [supervisors, setSupervisors] = useState<Supervisor[] | null>(null);
  const [supervisor, setSupervisor] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSupervisors()
      .then((list) => {
        setSupervisors(list);
        if (list.length === 1) setSupervisor(list[0].name);
      })
      .catch((e) => {
        setSupervisors([]);
        setError(e instanceof Error ? e.message : "Could not load supervisors");
      });
  }, []);

  const submit = async () => {
    const payload = getPreviewPayload();
    if (!supervisor || !pin || !payload) return;
    setBusy(true);
    setError("");
    try {
      const result = await authorisePriceFloor(payload, supervisor, pin);
      if (result.ok && result.token) {
        const name = supervisors?.find((s) => s.name === supervisor)?.full_name || supervisor;
        onAuthorised(result.token, name);
      } else {
        setError(result.message || "Wrong PIN");
        setPin("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Authorisation failed");
      setPin("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-gray-950/45 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-700">
        <div className="flex items-start justify-between border-b border-gray-100 px-6 py-5 dark:border-gray-800">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Supervisor authorisation</h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              A supervisor enters their PIN to allow these prices for this sale.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close supervisor dialog"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          className="space-y-4 px-6 py-5"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">
            Supervisor
            {supervisors === null ? (
              <div className="mt-1 flex items-center gap-2 text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading...
              </div>
            ) : supervisors.length === 0 ? (
              <p className="mt-1 text-sm text-gray-500">No supervisor has a POS Supervisor PIN set.</p>
            ) : (
              <select
                value={supervisor}
                onChange={(e) => setSupervisor(e.target.value)}
                className="mt-1 w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              >
                <option value="">Select a supervisor</option>
                {supervisors.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.full_name}
                  </option>
                ))}
              </select>
            )}
          </label>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">
            PIN
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
              className="mt-1 w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-lg tracking-widest text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />
          </label>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy || !supervisor || pin.length < 4}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-beveren-600 py-3 font-semibold text-white hover:bg-beveren-700 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Authorise
          </button>
        </form>
      </div>
    </div>
  );
}
