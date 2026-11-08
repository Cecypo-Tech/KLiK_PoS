import { describe, expect, it } from "vitest";
import { shouldRestorePersistedDiscount } from "./persistedDiscounts";

describe("shouldRestorePersistedDiscount", () => {
  it("does not restore a discount a Pricing Rule already took off the price", () => {
    // What get_cart_pricing writes: price is the discounted rate, original_price the
    // rate before it. Restoring discount_amount here subtracts the same 100 twice.
    expect(
      shouldRestorePersistedDiscount({ price: 2000, original_price: 2100, discount_amount: 100 }),
    ).toBe(false);
  });

  it("restores a discount carried on a held order, where price is still the full rate", () => {
    expect(shouldRestorePersistedDiscount({ price: 2000, discount_amount: 100 })).toBe(true);
  });

  it("restores when original_price matches price, so nothing came off yet", () => {
    expect(
      shouldRestorePersistedDiscount({ price: 2000, original_price: 2000, discount_amount: 100 }),
    ).toBe(true);
  });

  it("restores a percentage discount that is not yet in the price", () => {
    expect(shouldRestorePersistedDiscount({ price: 2000, discount_percentage: 5 })).toBe(true);
  });

  it("does not restore a percentage discount already in the price", () => {
    expect(
      shouldRestorePersistedDiscount({ price: 1900, original_price: 2000, discount_percentage: 5 }),
    ).toBe(false);
  });

  it("ignores a nonsensical original_price below the price", () => {
    expect(
      shouldRestorePersistedDiscount({ price: 2000, original_price: 1500, discount_amount: 100 }),
    ).toBe(true);
  });

  it("a custom-rate line's spent rule discount is not restored (it would come off the custom rate)", () => {
    // The custom rate itself is restored regardless; only the discount beside it is gated.
    expect(
      shouldRestorePersistedDiscount({ price: 2000, original_price: 2100, discount_amount: 100, custom_rate: 1800 }),
    ).toBe(false);
  });

  it("a custom-rate line's own discount from a held order is restored", () => {
    expect(
      shouldRestorePersistedDiscount({ price: 2000, original_price: 2000, discount_amount: 50, custom_rate: 1800 }),
    ).toBe(true);
  });
});
