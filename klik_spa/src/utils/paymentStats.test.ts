import { describe, it, expect } from "vitest";
import { computePaymentStats, type PaymentStat } from "./paymentStats";
import type { SalesInvoice } from "../../types";
import type { PaymentMode } from "../hooks/usePaymentModes";

function statFor(stats: Record<string, PaymentStat>, name: string): PaymentStat {
  const stat = stats[name];
  if (!stat) throw new Error(`Expected a payment stat for "${name}"`);
  return stat;
}

type Invoice = Pick<SalesInvoice, "payment_methods" | "paymentMethod" | "totalAmount" | "status">;

const mode = (over: Partial<PaymentMode> = {}): PaymentMode => ({
  mode_of_payment: "Cash",
  default: 1,
  ...over,
});

const invoice = (over: Partial<Invoice> = {}): Invoice => ({
  paymentMethod: "Cash",
  totalAmount: 0,
  status: "Paid" as SalesInvoice["status"],
  ...over,
});

describe("computePaymentStats", () => {
  it("does not double the drawer total when the opening float is zero", () => {
    // Regression: a single KES 450 Cash sale with no starting float used to
    // show KES 900 because mode.amount (the backend's sales total) was
    // wrongly read as the opening float and added a second time.
    const modes = [mode({ name: "Cash", openingAmount: 0, amount: 450 })];
    const invoices = [invoice({ paymentMethod: "Cash", totalAmount: 450 })];

    const stats = computePaymentStats(modes, invoices);

    expect(statFor(stats, "Cash").amount).toBe(450);
    expect(statFor(stats, "Cash").transactions).toBe(1);
  });

  it("adds a genuine opening float to the invoice sales total", () => {
    const modes = [mode({ name: "Cash", openingAmount: 100, amount: 0 })];
    const invoices = [invoice({ paymentMethod: "Cash", totalAmount: 450 })];

    const stats = computePaymentStats(modes, invoices);

    expect(statFor(stats, "Cash").amount).toBe(550);
  });

  it("sums split payment methods on a single invoice without double counting", () => {
    const modes = [
      mode({ name: "Cash", openingAmount: 0, amount: 200 }),
      mode({ name: "Card", openingAmount: 0, amount: 250 }),
    ];
    const invoices = [
      invoice({
        totalAmount: 450,
        payment_methods: [
          { mode_of_payment: "Cash", amount: 200 },
          { mode_of_payment: "Card", amount: 250 },
        ],
      }),
    ];

    const stats = computePaymentStats(modes, invoices);

    expect(statFor(stats, "Cash").amount).toBe(200);
    expect(statFor(stats, "Card").amount).toBe(250);
    expect(statFor(stats, "Cash").transactions).toBe(1);
    expect(statFor(stats, "Card").transactions).toBe(0);
  });

  it("subtracts returns from the mode total", () => {
    const modes = [mode({ name: "Cash", openingAmount: 0, amount: 0 })];
    const invoices = [
      invoice({ paymentMethod: "Cash", totalAmount: 450 }),
      invoice({ paymentMethod: "Cash", totalAmount: 450, status: "Return" as SalesInvoice["status"] }),
    ];

    const stats = computePaymentStats(modes, invoices);

    expect(statFor(stats, "Cash").amount).toBe(0);
  });
});
