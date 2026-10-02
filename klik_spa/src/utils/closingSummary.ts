/**
 * The Closing Shift screen's expected amounts, from the server
 * (klik_pos.api.pos_entry.closing_summary): the figures the closing entry is filed with,
 * whatever the invoice table has loaded or is filtered to.
 */

export interface ClosingSummaryMode {
  mode_of_payment: string;
  opening_amount: number;
  sales_amount: number;
  expected_amount: number;
  transactions: number;
}

export interface ClosingSummary {
  opening_entry: string;
  modes: ClosingSummaryMode[];
  /** The till's 'Hide Expected Amount': takings and expected amounts are left out (0). */
  figures_hidden: boolean;
}

export interface PaymentStat {
  name: string;
  openingAmount: number;
  /** Expected in the drawer at close: opening float plus the shift's takings. */
  amount: number;
  transactions: number;
}

/** One stat per mode: the till's modes first (in its order), then any other mode that took money. */
export function closingStats(summary: ClosingSummary | null, tillModes: string[]): Record<string, PaymentStat> {
  if (!summary) return {};
  const stats: Record<string, PaymentStat> = {};
  for (const name of tillModes) {
    if (name) stats[name] = { name, openingAmount: 0, amount: 0, transactions: 0 };
  }
  for (const mode of summary.modes) {
    stats[mode.mode_of_payment] = {
      name: mode.mode_of_payment,
      openingAmount: Number(mode.opening_amount || 0),
      amount: Number(mode.expected_amount || 0),
      transactions: Number(mode.transactions || 0),
    };
  }
  return stats;
}
