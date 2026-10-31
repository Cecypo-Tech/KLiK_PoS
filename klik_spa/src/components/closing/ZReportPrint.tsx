import { useQzPrint } from "../../hooks/useQzPrint";
import QzRulePicker from "../QzRulePicker";

/** Whether the till offers the Z-report print after a close: QZ is on and the user may close. */
export const canPrintZReport = (
  posDetails: { custom_enable_qz_print?: unknown } | null | undefined,
  userInfo: { can_close_shift?: boolean } | null | undefined,
) => !!posDetails?.custom_enable_qz_print && userInfo?.can_close_shift !== false;

/** Shown in place of the instant redirect once the shift is closed, so the cashier can print the Z-report. */
export default function ZReportPrint({ name, onContinue }: { name: string; onContinue: () => void }) {
  const qz = useQzPrint(name, false, false, "POS Closing Entry");
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow max-w-md text-center">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white">Shift closed</h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{name}</p>
        <button type="button" onClick={qz.start} disabled={qz.busy}
          className="mt-4 mr-2 px-4 py-2 bg-beveren-600 text-white rounded-md hover:bg-beveren-700 disabled:opacity-50">
          Print Z-report
        </button>
        <button type="button" onClick={onContinue}
          className="mt-4 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-200">
          Continue
        </button>
        <QzRulePicker {...qz.picker} />
      </div>
    </div>
  );
}
