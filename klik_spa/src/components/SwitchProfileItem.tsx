import { useEffect, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { toast } from "react-toastify";
import { fetchCurrentShiftState, leaveShift, type CurrentShiftState } from "../services/opeiningEntry";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useCartStore } from "../stores/cartStore";
import { switchProfileState } from "../utils/switchProfile";

/**
 * "Switch profile": steps out of the shift the cashier works in and reloads to the opening
 * screen, where they pick another of their profiles - or the same one, to come back. The
 * shift stays open; anyone still in it, or a manager, closes it. `menu` is the user menu's
 * row (rendered inside the open menu, so the shift is read fresh each time it opens);
 * `button` sits beside Close Shift on the closing screen.
 */
export default function SwitchProfileItem({ variant = "menu", compact = false }: { variant?: "menu" | "button"; compact?: boolean }) {
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
    window.location.assign("/klik_pos/pos");
  };

  const confirmBox = (
    <>
      <p className="text-gray-700 dark:text-gray-200">
        Leave this shift? It stays open. Anyone still in it, or a manager, can close it.
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
    </>
  );

  if (variant === "button") {
    return (
      <div className="relative">
        <button
          type="button"
          disabled={!!blocked}
          title={blocked ?? undefined}
          onClick={() => setConfirming((open) => !open)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <ArrowLeftRight className="w-4 h-4" />
          <span>Switch Profile</span>
        </button>
        {confirming && (
          <div className="absolute right-0 top-full mt-2 w-72 z-[100] p-3 text-sm rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            {confirmBox}
          </div>
        )}
      </div>
    );
  }

  if (confirming) {
    return <div className="px-4 py-3 text-sm bg-gray-50 dark:bg-gray-700/50">{confirmBox}</div>;
  }

  return (
    <button
      type="button"
      disabled={!!blocked}
      title={blocked ?? undefined}
      onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
      className={`flex items-center w-full px-4 ${compact ? "py-2" : "py-3"} text-sm text-left transition-colors ${blocked ? "text-gray-400 dark:text-gray-500 cursor-not-allowed" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
    >
      <ArrowLeftRight size={compact ? 14 : 16} className="mr-3 shrink-0 text-gray-500 dark:text-gray-400" />
      <span className="min-w-0">
        <span className="block">Switch profile</span>
        {blocked && <span className="block text-xs">{blocked}</span>}
      </span>
    </button>
  );
}
