import { Children } from "react";
import type { ReactNode } from "react";

/**
 * The small money fields beside the payment summary - delivery charge, discount, loyalty.
 * Their values are short, so they sit as label/input rows in half the width instead of
 * a full-width row each. Renders nothing when the profile enables none of them.
 */
export default function OtherCharges({ children }: { children: ReactNode }) {
  const rows = Children.toArray(children);
  if (rows.length === 0) return null;
  return (
    <div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Other charges</h3>
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">{rows}</div>
    </div>
  );
}
