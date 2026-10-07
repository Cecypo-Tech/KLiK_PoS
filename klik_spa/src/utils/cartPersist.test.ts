import { describe, expect, it } from "vitest";

import { persistedCartState } from "./cartPersist";

describe("persistedCartState", () => {
  it("saves the cart but not passing UI state, so a reload never reopens or replays it", () => {
    const saved = persistedCartState({
      cartItems: [],
      selectedCustomer: null,
      expandedCartItemId: "L1",
      pendingRateOverrides: [{ itemId: "L1" }],
      rateOverrideNonce: 3,
      additionalInfoOpen: true,
    });
    expect(saved).toEqual({ cartItems: [], selectedCustomer: null });
  });
});
