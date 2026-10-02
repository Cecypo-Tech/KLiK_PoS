import { describe, expect, it } from "vitest";

import { closingStats, type ClosingSummary } from "./closingSummary";

const summary: ClosingSummary = {
  opening_entry: "POS-OPE-1",
  figures_hidden: false,
  modes: [
    { mode_of_payment: "Cash", opening_amount: 1000, sales_amount: 500, expected_amount: 1500, transactions: 3 },
    // Took money but is not on the till: still counted.
    { mode_of_payment: "Bank", opening_amount: 0, sales_amount: 200, expected_amount: 200, transactions: 1 },
  ],
};

describe("closingStats", () => {
  it("shows the server's expected amount per mode, the till's modes first", () => {
    const stats = closingStats(summary, ["M-Pesa", "Cash"]);
    expect(Object.keys(stats)).toEqual(["M-Pesa", "Cash", "Bank"]);
    expect(stats.Cash).toEqual({ name: "Cash", openingAmount: 1000, amount: 1500, transactions: 3 });
    expect(stats["M-Pesa"]).toEqual({ name: "M-Pesa", openingAmount: 0, amount: 0, transactions: 0 });
    expect(stats.Bank?.amount).toBe(200);
  });

  it("has nothing to show before the summary arrives", () => {
    expect(closingStats(null, ["Cash"])).toEqual({});
  });
});
