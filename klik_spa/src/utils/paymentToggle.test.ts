import { describe, expect, it } from "vitest";
import { followTotal, toggleOn } from "./paymentToggle";

describe("toggleOn", () => {
  it("fills what is still owed, leaving the other rows alone", () => {
    expect(toggleOn({ Cash: 1000, "Mpesa-1": 0 }, "Mpesa-1", 4002)).toEqual({ Cash: 1000, "Mpesa-1": 3002 });
  });

  it("switches the method when one other row already holds the whole sale", () => {
    // Cash is pre-filled with the total; ticking M-Pesa means "pay by M-Pesa instead".
    expect(toggleOn({ Cash: 4002, "Mpesa-1": 0 }, "Mpesa-1", 4002)).toEqual({ Cash: 0, "Mpesa-1": 4002 });
  });

  it("leaves a split across several rows alone when nothing is owed", () => {
    expect(toggleOn({ Cash: 2000, Cheque: 2002, "Mpesa-1": 0 }, "Mpesa-1", 4002)).toEqual({
      Cash: 2000,
      Cheque: 2002,
      "Mpesa-1": 0,
    });
  });

  it("does not move an overpayment larger than the sale", () => {
    // Cash tendered 5000 for a 4002 sale is change for the customer, not M-Pesa money.
    expect(toggleOn({ Cash: 5000, "Mpesa-1": 0 }, "Mpesa-1", 4002)).toEqual({ Cash: 5000, "Mpesa-1": 0 });
  });

  it("never takes over from a row that picked receipts or a completed STK push stand behind", () => {
    // M-Pesa holds the sale from a picked receipt; ticking Cash must not quietly move it,
    // or the receipt is consumed for a sale that took nothing from it.
    expect(toggleOn({ Cash: 0, "Mpesa-1": 4002 }, "Cash", 4002, ["Mpesa-1"])).toEqual({ Cash: 0, "Mpesa-1": 4002 });
  });
});

describe("followTotal", () => {
  it("moves the one method that paid the whole sale to the new total - M-Pesa as much as Cash", () => {
    // M-Pesa ticked for 560, then a 556 discount: the push must ask for 4, not 560.
    expect(followTotal({ Cash: 0, "Mpesa-1": 560 }, 560, 4)).toEqual({ Cash: 0, "Mpesa-1": 4 });
    expect(followTotal({ Cash: 560 }, 560, 4)).toEqual({ Cash: 4 });
  });

  it("follows a rise too, as with a delivery charge added", () => {
    expect(followTotal({ "Mpesa-1": 560 }, 560, 760)).toEqual({ "Mpesa-1": 760 });
  });

  it("leaves a split alone", () => {
    expect(followTotal({ Cash: 300, "Mpesa-1": 260 }, 560, 4)).toEqual({ Cash: 300, "Mpesa-1": 260 });
  });

  it("leaves an amount the cashier set away from the total alone", () => {
    expect(followTotal({ Cash: 1000 }, 560, 4)).toEqual({ Cash: 1000 });
  });

  it("leaves a method whose money is already asked for or paid alone", () => {
    // A push for 560 is waiting on, or was paid by, the customer: the amount is that push's.
    expect(followTotal({ "Mpesa-1": 560 }, 560, 4, "Mpesa-1")).toEqual({ "Mpesa-1": 560 });
  });

  it("has nothing to move when nothing is paid", () => {
    expect(followTotal({}, 560, 4)).toEqual({});
  });
});
