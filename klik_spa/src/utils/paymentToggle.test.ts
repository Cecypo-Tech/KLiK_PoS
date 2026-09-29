import { describe, expect, it } from "vitest";
import { toggleOn } from "./paymentToggle";

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
});
