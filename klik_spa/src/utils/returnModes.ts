/**
 * Refund modes for a return. Only cash is handed back at the till: card and M-Pesa money
 * goes back through accounts as a Payment Entry reversal, so those modes are never offered
 * (the server refuses them too).
 */
type ModeLike = { mode_of_payment: string; type?: string; default?: number | boolean };

export function cashRefundModes<T extends ModeLike>(modes: T[]): T[] {
  return modes.filter((mode) => (mode.type || "").toLowerCase() === "cash");
}

/** The till's default mode if it is cash, else its first cash mode, else "". */
export function defaultCashRefundMode(modes: ModeLike[]): string {
  const cash = cashRefundModes(modes);
  return (cash.find((mode) => Number(mode.default) === 1) || cash[0])?.mode_of_payment || "";
}
