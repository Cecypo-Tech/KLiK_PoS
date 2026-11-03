import { describe, expect, it } from "vitest";

import { paymentShortfallError } from "./paymentShortfall";

const base = { total: 3200, paid: 2500, allowPartial: false, isWalkin: false, symbol: "Sh" };

describe("paymentShortfallError", () => {
  it("refuses an underpayment on a till that does not allow part payment", () => {
    expect(paymentShortfallError(base)).toMatch(/Insufficient payment.*Remaining: Sh 700/);
  });

  it("lets a named customer part-pay on a till that allows it", () => {
    expect(paymentShortfallError({ ...base, allowPartial: true })).toBeNull();
  });

  it("still wants some money: an unpaid sale is a credit sale", () => {
    expect(paymentShortfallError({ ...base, allowPartial: true, paid: 0 })).toMatch(/Enter a payment/);
  });

  it("never leaves a balance on the walk-in customer", () => {
    expect(paymentShortfallError({ ...base, allowPartial: true, isWalkin: true })).toMatch(/named customer/);
  });

  it("passes a sale paid in full", () => {
    expect(paymentShortfallError({ ...base, paid: 3200 })).toBeNull();
  });
});
