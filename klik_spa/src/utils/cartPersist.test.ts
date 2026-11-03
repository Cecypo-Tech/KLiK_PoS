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

  it("saves no order once its sale is complete, so a reload starts a new sale", () => {
    const saved = persistedCartState({
      cartItems: [{ id: "L1" }],
      selectedCustomer: { id: "C1" },
      selectedPriceList: "Elite",
      checkoutExtras: { deliveryCharge: 50 },
      saleCompleted: true,
      viewMode: "list",
    });
    expect(saved).toEqual({ viewMode: "list" });
  });
});
