import { describe, expect, it } from "vitest";
import {
  EMPTY_CHECKOUT_EXTRAS, checkoutExtrasFromHeldOrder, heldOrderPayloadExtras, tillFlags,
} from "./heldOrderPayload";

const allOn = { deliveryCharge: true, shippingRule: true, discountChange: true };
const extras = {
  deliveryCharge: 250, deliveryPersonnel: "DP-0001", orderDiscountAmount: 100, salesTaxCharges: "VAT 16% - AP",
  remarks: "Deliver after 4pm",
};

describe("tillFlags", () => {
  it("reads the POS Profile's switches however they arrive", () => {
    expect(tillFlags({ custom_enable_delivery_charge: 1, custom_enable_shipping_rule: "1", allow_discount_change: true }))
      .toEqual(allOn);
    expect(tillFlags({})).toEqual({ deliveryCharge: false, shippingRule: false, discountChange: false });
    expect(tillFlags(null)).toEqual({ deliveryCharge: false, shippingRule: false, discountChange: false });
  });
});

describe("heldOrderPayloadExtras", () => {
  it("sends the buyer, every extra field, and the checkout state", () => {
    expect(
      heldOrderPayloadExtras({
        walkin: { name: " Jane Wanjiku ", taxId: "P051234567X", phone: "0712345678" },
        extraFields: { po_no: "PO-88", custom_site_ref: "Block C" },
        shippingRule: null,
        extras,
        flags: allOn,
      }),
    ).toEqual({
      tax_id: "P051234567X",
      walkin_name: "Jane Wanjiku",
      walkin_phone: "0712345678",
      extra_fields: { po_no: "PO-88", custom_site_ref: "Block C" },
      shipping_rule: null,
      deliveryCharge: 250,
      deliveryPersonnel: "DP-0001",
      orderDiscountAmount: 100,
      SalesTaxCharges: "VAT 16% - AP",
      remarks: "Deliver after 4pm",
    });
  });

  it("sends blanks as null and nothing it does not have", () => {
    const out = heldOrderPayloadExtras({
      walkin: { name: "  " }, extraFields: undefined, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn,
    });
    expect(out.walkin_name).toBeNull();
    expect(out.tax_id).toBeNull();
    expect(out.extra_fields).toEqual({});
    expect(out.deliveryCharge).toBe(0);
    expect(out.deliveryPersonnel).toBeNull();
    // Always sent, so holding again with the box emptied clears the order's remarks.
    expect(out.remarks).toBe("");
  });

  it("sends remarks trimmed", () => {
    const out = heldOrderPayloadExtras({
      walkin: {}, extraFields: {}, shippingRule: null, extras: { ...extras, remarks: "  Fragile \n" }, flags: allOn,
    });
    expect(out.remarks).toBe("Fragile");
  });

  it("drops a delivery charge the till does not allow - the server would refuse the hold", () => {
    const out = heldOrderPayloadExtras({
      walkin: {}, extraFields: {}, shippingRule: null, extras, flags: { ...allOn, deliveryCharge: false },
    });
    expect(out.deliveryCharge).toBe(0);
  });

  it("sends a shipping rule instead of a delivery charge, never both", () => {
    const out = heldOrderPayloadExtras({ walkin: {}, extraFields: {}, shippingRule: "Nairobi CBD", extras, flags: allOn });
    expect(out.shipping_rule).toBe("Nairobi CBD");
    expect(out.deliveryCharge).toBe(0);
  });

  it("drops a shipping rule on a till that has them off", () => {
    const out = heldOrderPayloadExtras({
      walkin: {}, extraFields: {}, shippingRule: "Nairobi CBD", extras, flags: { ...allOn, shippingRule: false },
    });
    expect(out.shipping_rule).toBeNull();
    expect(out.deliveryCharge).toBe(250);
  });
});

describe("checkoutExtrasFromHeldOrder", () => {
  const details = {
    discount_amount: 100,
    remarks: "Deliver after 4pm",
    cart_meta: { deliveryCharge: 250, deliveryPersonnel: "DP-0001", SalesTaxCharges: "VAT 16% - AP" },
  };

  it("restores what the order was held with", () => {
    expect(checkoutExtrasFromHeldOrder(details, allOn)).toEqual(extras);
  });

  it("restores no delivery charge or discount a till no longer allows", () => {
    const out = checkoutExtrasFromHeldOrder(details, { ...allOn, deliveryCharge: false, discountChange: false });
    expect(out.deliveryCharge).toBe(0);
    expect(out.orderDiscountAmount).toBe(0);
    expect(out.deliveryPersonnel).toBe("DP-0001");
  });

  it("takes the remarks from the cart meta when the order carries none of its own", () => {
    const out = checkoutExtrasFromHeldOrder({ cart_meta: { remarks: "From meta" } }, allOn);
    expect(out.remarks).toBe("From meta");
  });

  it("copes with an order held before any of this existed", () => {
    expect(checkoutExtrasFromHeldOrder({ cart_meta: null }, allOn)).toEqual(EMPTY_CHECKOUT_EXTRAS);
  });
});
