import { roundCurrency } from "./currencyMath";

/**
 * At closing, the cashier says how much of the counted cash is handed over for banking. The
 * rest stays in the drawer as the float, and that - not the whole count - is what the next
 * opening on this till is suggested at. Only Cash-type modes keep money in the drawer; the
 * server refuses banking on any other mode, and more than was counted.
 */
export function leftInDrawer(counted: number, banked: number): number {
  return roundCurrency((counted || 0) - (banked || 0));
}

export function bankingError(counted: number, banked: number): string | null {
  if ((banked || 0) < 0) return "The amount to bank cannot be negative.";
  if (roundCurrency(banked || 0) > roundCurrency(counted || 0)) return "That is more than was counted.";
  return null;
}

export function closingBalancePayload(
  counted: Record<string, number>,
  banked: Record<string, number>,
  floatModes: Set<string>,
): { mode_of_payment: string; closing_amount: number; banked_amount?: number }[] {
  return Object.entries(counted).map(([mode_of_payment, closing_amount]) => {
    const toBank = floatModes.has(mode_of_payment) ? banked[mode_of_payment] || 0 : 0;
    return toBank
      ? { mode_of_payment, closing_amount: closing_amount || 0, banked_amount: toBank }
      : { mode_of_payment, closing_amount: closing_amount || 0 };
  });
}

export function floatModeNames(modes: { name?: string; mode_of_payment?: string; type?: string }[]): Set<string> {
  return new Set(
    modes.filter((m) => m.type === "Cash").map((m) => m.name || m.mode_of_payment || "").filter(Boolean),
  );
}
