import { describe, expect, it } from "vitest";
import type { FixedCharge, InvoiceForReturn, ReturnItem } from "../services/returnService";
import {
  everyAvailableQtySelected,
  fixedChargeReturned,
  refundDefault,
  returnedValue,
  returnsAnyFixedCharge,
} from "./returnFixedCharges";

const item = (code: string, qty: number, rate: number, extra: Partial<ReturnItem> = {}): ReturnItem => ({
  item_code: code,
  item_name: code,
  qty,
  rate,
  amount: qty * rate,
  returned_qty: 0,
  available_qty: qty,
  ...extra,
});

const fee = (extra: Partial<FixedCharge> = {}): FixedCharge => ({
  description: "Courier",
  account_head: "Courier - DC",
  amount: 150,
  reversed_by: null,
  ...extra,
});

const invoice = (items: ReturnItem[], fixed_charges: FixedCharge[] = [], paid_amount?: number): InvoiceForReturn => ({
  name: "POS-1",
  posting_date: "2026-09-22",
  posting_time: "10:00:00",
  customer: "Walk In",
  grand_total: items.reduce((s, i) => s + i.amount, 0) + fixed_charges.reduce((s, c) => s + c.amount, 0),
  paid_amount,
  status: "Paid",
  items,
  fixed_charges,
});

describe("everyAvailableQtySelected", () => {
  it("is true only when every returnable quantity is chosen", () => {
    expect(everyAvailableQtySelected(invoice([item("A", 2, 100, { return_qty: 2 }), item("B", 1, 50, { return_qty: 1 })]))).toBe(true);
    expect(everyAvailableQtySelected(invoice([item("A", 2, 100, { return_qty: 1 }), item("B", 1, 50, { return_qty: 1 })]))).toBe(false);
  });

  it("ignores lines that were already fully returned", () => {
    const gone = item("B", 1, 50, { returned_qty: 1, available_qty: 0 });
    expect(everyAvailableQtySelected(invoice([item("A", 2, 100, { return_qty: 2 }), gone]))).toBe(true);
  });

  it("is false with nothing selected", () => {
    expect(everyAvailableQtySelected(invoice([item("A", 2, 100)]))).toBe(false);
  });
});

describe("fixedChargeReturned", () => {
  it("mirrors the quantity rule until the cashier ticks it", () => {
    expect(fixedChargeReturned(fee(), invoice([item("A", 2, 100, { return_qty: 2 })]))).toBe(true);
    expect(fixedChargeReturned(fee(), invoice([item("A", 2, 100, { return_qty: 1 })]))).toBe(false);
  });

  it("follows the cashier's tick over the rule", () => {
    expect(fixedChargeReturned(fee({ return_charge: true }), invoice([item("A", 2, 100, { return_qty: 1 })]))).toBe(true);
    expect(fixedChargeReturned(fee({ return_charge: false }), invoice([item("A", 2, 100, { return_qty: 2 })]))).toBe(false);
  });

  it("never returns a fee an earlier credit note took back", () => {
    expect(fixedChargeReturned(fee({ reversed_by: "X-POS-1", return_charge: true }), invoice([item("A", 2, 100, { return_qty: 2 })]))).toBe(false);
  });
});

describe("returnedValue and refundDefault", () => {
  it("adds a ticked fee to the returned items", () => {
    const inv = invoice([item("A", 2, 100, { return_qty: 1 })], [fee({ return_charge: true })]);
    expect(returnedValue(inv)).toBe(250);
    expect(returnsAnyFixedCharge(inv)).toBe(true);
  });

  it("leaves an unticked fee out", () => {
    const inv = invoice([item("A", 2, 100, { return_qty: 1 })], [fee()]);
    expect(returnedValue(inv)).toBe(100);
    expect(returnsAnyFixedCharge(inv)).toBe(false);
  });

  it("scales what was paid by the share of the sale coming back, fee included", () => {
    // Sold 200 of items + 150 fee, paid 406 (VAT on top). One item and the fee: 250/350 of 406.
    const inv = invoice([item("A", 2, 100, { return_qty: 1 })], [fee({ return_charge: true })], 406);
    expect(refundDefault(inv)).toBe(290);
    // Everything: the whole payment.
    expect(refundDefault(invoice([item("A", 2, 100, { return_qty: 2 })], [fee()], 406))).toBe(406);
  });

  it("falls back to the grand total when nothing was recorded as paid", () => {
    expect(refundDefault(invoice([item("A", 2, 100, { return_qty: 2 })]))).toBe(200);
  });
});
