import { useEffect, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { toast } from "react-toastify";
import { fetchCurrentShiftState, leaveShift, type CurrentShiftState } from "../services/opeiningEntry";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useCartStore } from "../stores/cartStore";
import { switchProfileState } from "../utils/switchProfile";

/**
 * The user menu's "Switch profile": leaves the shift the cashier joined and reloads to the
 * opening screen, where they pick another of their profiles. The shift stays open for the
 * till. Rendered inside the open menu, so the shift is read fresh each time it opens.
 */
export default function SwitchProfileItem({ compact = false }: { compact?: boolean }) {
  const posProfiles = usePOSProfileStore((s) => s.posProfiles);
  const fetchPOSProfiles = usePOSProfileStore((s) => s.fetchPOSProfiles);
  const clearCache = usePOSProfileStore((s) => s.clearCache);
  const cartCount = useCartStore((s) => s.cartItems.length);
  const [shift, setShift] = useState<CurrentShiftState | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    fetchCurrentShiftState().then(setShift);
    if (posProfiles.length === 0) fetchPOSProfiles();
  }, [posProfiles.length, fetchPOSProfiles]);

  const { show, blocked } = switchProfileState({ profileCount: posProfiles.length, shift, cartCount });
  if (!show) return null;

  const row = `flex items-center w-full px-4 ${compact ? "py-2" : "py-3"} text-sm text-left transition-colors`;

  const leave = async () => {
    setLeaving(true);
    const result = await leaveShift();
    if (!result.ok) {
      setLeaving(false);
      toast.error(result.error);
      return;
    }
    // The cached profile belongs to the shift just left.
    clearCache();
    window.location.reload();
  };

  if (confirming) {
    return (
      <div className="px-4 py-3 text-sm bg-gray-50 dark:bg-gray-700/50">
        <p className="text-gray-700 dark:text-gray-200">
          Leave this shift? It stays open for {shift?.opened_by_name || shift?.opened_by}.
        </p>
        <div className="mt-2 flex justify-end gap-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setConfirming(false); }}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={leaving}
            onClick={(e) => { e.stopPropagation(); leave(); }}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-beveren-600 text-white hover:bg-beveren-700 disabled:opacity-60"
          >
            {leaving ? "Leaving..." : "Switch"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled={!!blocked}
      title={blocked ?? undefined}
      onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
      className={`${row} ${blocked ? "text-gray-400 dark:text-gray-500 cursor-not-allowed" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
    >
      <ArrowLeftRight size={compact ? 14 : 16} className="mr-3 shrink-0 text-gray-500 dark:text-gray-400" />
      <span className="min-w-0">
        <span className="block">Switch profile</span>
        {blocked && <span className="block text-xs">{blocked}</span>}
      </span>
    </button>
  );
}
