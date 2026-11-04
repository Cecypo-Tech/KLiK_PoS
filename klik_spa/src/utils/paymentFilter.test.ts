import { describe, expect, it } from "vitest";
import { matchesPaymentFilter } from "./paymentFilter";

describe("matchesPaymentFilter", () => {
  it("lets every row through on All", () => {
    expect(matchesPaymentFilter({ paymentMethod: "Cash" }, "all")).toBe(true);
  });

  it("keeps only rows paid that way", () => {
    expect(matchesPaymentFilter({ paymentMethod: "Cash" }, "Cash")).toBe(true);
    expect(matchesPaymentFilter({ paymentMethod: "M-Pesa" }, "Cash")).toBe(false);
  });

  it("never hides a held order or a quote, which have no payment yet", () => {
    expect(matchesPaymentFilter({ paymentMethod: "-", isHeldOrder: true }, "Cash")).toBe(true);
    expect(matchesPaymentFilter({ paymentMethod: "-", isQuote: true }, "Cash")).toBe(true);
  });
});
