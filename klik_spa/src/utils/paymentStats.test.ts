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

describe("computePaymentStats and money from outside the POS", () => {
  it("counts an advance only when its Payment Entry was stamped with this shift", () => {
    // 100 Cash at the till; 100 by M-Pesa receipt taken at the till (stamped with the
    // shift); 150 a customer advance an accountant recorded (no shift). The last was
    // never in the cashier's hands, so it is shown on the invoice but not counted.
    const modes = [mode({ name: "Cash", openingAmount: 0 }), mode({ name: "Cheque", mode_of_payment: "Cheque", openingAmount: 0 })];
    const invoices = [
      invoice({
        paymentMethod: "Cash",
        totalAmount: 350,
        payment_methods: [
          { mode_of_payment: "Cash", amount: 100 },
          { mode_of_payment: "Cheque", amount: 100, payment_entry: "PE-TILL", pos_opening_entry: "OPE-1" },
          { mode_of_payment: "Cheque", amount: 150, payment_entry: "PE-OUTSIDE", pos_opening_entry: null },
        ],
      }),
    ];

    const stats = computePaymentStats(modes, invoices, "OPE-1");

    expect(statFor(stats, "Cash").amount).toBe(100);
    expect(statFor(stats, "Cheque").amount).toBe(100);
  });
});
