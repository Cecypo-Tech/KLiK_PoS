import { describe, expect, it } from "vitest";
import { openingPaymentAmounts } from "./paymentDefaults";

const modes = [
  { mode_of_payment: "Mpesa-1", default: 0 },
  { mode_of_payment: "Cash", default: 1 },
];

describe("openingPaymentAmounts", () => {
  it("puts the grand total on the default mode when the till asks for it", () => {
    expect(openingPaymentAmounts(modes, 850, true)).toEqual({ Cash: 850 });
  });

  it("leaves every mode empty when 'Set Grand Total to Default Payment Method' is off", () => {
    expect(openingPaymentAmounts(modes, 850, false)).toEqual({});
  });

  it("leaves every mode empty when no mode is the default, even with the setting on", () => {
    // Never the first mode by position: that is a guess, not the till's setting.
    expect(openingPaymentAmounts([{ mode_of_payment: "Cash", default: 0 }], 850, true)).toEqual({});
  });
});
