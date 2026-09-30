import { describe, expect, it } from "vitest";
import { taxPreviewStep } from "./taxPreviewStep";

const ready = { isOpen: true, invoiceSubmitted: false, hasCustomer: true, cartCount: 2 };

describe("taxPreviewStep", () => {
  it("fetches a preview for an open checkout with a customer and a cart", () => {
    expect(taxPreviewStep(ready)).toBe("fetch");
  });

  it("keeps the last preview once the sale is submitted", () => {
    // The preview describes exactly the cart that was sold; dropping it made the completed
    // screen fall back to arithmetic that knows nothing of the server's tax.
    expect(taxPreviewStep({ ...ready, invoiceSubmitted: true })).toBe("keep");
  });

  it("clears when the checkout closes, has no customer, or the cart is empty", () => {
    expect(taxPreviewStep({ ...ready, isOpen: false })).toBe("clear");
    expect(taxPreviewStep({ ...ready, hasCustomer: false })).toBe("clear");
    expect(taxPreviewStep({ ...ready, cartCount: 0 })).toBe("clear");
    expect(taxPreviewStep({ ...ready, invoiceSubmitted: true, cartCount: 0 })).toBe("clear");
  });
});
