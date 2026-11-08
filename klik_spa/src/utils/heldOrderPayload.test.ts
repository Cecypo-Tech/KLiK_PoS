import { describe, expect, it } from "vitest";
import {
  EMPTY_CHECKOUT_EXTRAS, buildOrderPayload, checkoutExtrasFromHeldOrder, heldItemToCartItem, heldOrderPayloadExtras,
  tillFlags,
  heldItemsToCart,
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

  it("keeps a note cleared in desk cleared, whatever the cart copy says", () => {
    const out = checkoutExtrasFromHeldOrder({ remarks: "", cart_meta: { remarks: "Stale" } }, allOn);
    expect(out.remarks).toBe("");
  });

  it("copes with an order held before any of this existed", () => {
    expect(checkoutExtrasFromHeldOrder({ cart_meta: null }, allOn)).toEqual(EMPTY_CHECKOUT_EXTRAS);
  });
});

describe("heldItemToCartItem", () => {
  it("keeps the price list the line was priced from, so the minimum is judged on it", () => {
    const line = heldItemToCartItem({ item_code: "H4", item_name: "H4 Bulb", quantity: 1, price: 400, selectedPriceList: "Distributor" });
    expect((line as unknown as { selected_price_list?: string }).selected_price_list).toBe("Distributor");
    const plain = heldItemToCartItem({ item_code: "H4", item_name: "H4 Bulb", quantity: 1, price: 450 });
    expect((plain as unknown as { selected_price_list?: string }).selected_price_list).toBeUndefined();
  });

  it("keeps the Loss of Sale split the server worked out at this till", () => {
    const line = heldItemToCartItem({ item_code: "F049", item_name: "Filter", quantity: 40, los_qty: 60, price: 450 });
    expect(line.quantity).toBe(40);
    expect(line.los_qty).toBe(60);
  });

  it("an order from before the split opens with no Loss of Sale", () => {
    expect(heldItemToCartItem({ item_code: "F049", quantity: 100, price: 450 }).los_qty).toBe(0);
  });
});

describe("buildOrderPayload", () => {
  it("sends the item code as id for a second line of the same item", () => {
    const payload = buildOrderPayload({
      cartItems: [{ id: "PEN-1731000000000", item_code: "PEN", quantity: 1, price: 10 }],
      itemDiscounts: {},
      effectiveRate: () => 10,
      customer: { id: "C" },
      totals: { subtotal: 10, grandTotal: 10, taxAmount: 0, isInclusive: false, couponDiscount: 0 },
      appliedCoupons: [],
      businessType: "B2C",
      salesperson: null,
      sellingPriceList: null,
      extras: { walkin: {}, extraFields: {}, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn },
      loyalty: null,
    });
    expect(payload.items[0]).toMatchObject({ id: "PEN", item_code: "PEN" });
  });

  // The payload checkout's Hold sent before it was moved here; Save Quote sends the same.
  it("builds Hold's payload for a sample cart", () => {
    const customer = { id: "CUST-1", name: "Acme" };
    const itemDiscounts = { A: { discountPercentage: 10, selectedPriceList: "Wholesale" } };
    const payload = buildOrderPayload({
      cartItems: [
        { id: "A", item_code: "A", quantity: 2, price: 100, originalPrice: 100, discountedPriceExcl: 90 },
        { id: "B", quantity: 1, price: 50, discount_amount: 5 },
      ],
      itemDiscounts,
      effectiveRate: () => 45,
      customer,
      totals: { subtotal: 225, grandTotal: 261, taxAmount: 36, isInclusive: false, couponDiscount: 0 },
      appliedCoupons: [],
      businessType: "B2C",
      salesperson: "SP-1",
      sellingPriceList: "Standard Selling",
      extras: { walkin: {}, extraFields: {}, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn },
      loyalty: null,
    });

    expect(payload).toEqual({
      items: [
        {
          id: "A", line_id: "A", item_code: "A", quantity: 2, price: 90, originalPrice: 100, discountedPriceExcl: 90,
          discountPercentage: 10, discountAmount: 0, selectedPriceList: "Wholesale",
        },
        {
          id: "B", line_id: "B", item_code: "B", quantity: 1, price: 45, discount_amount: 5,
          discountPercentage: 0, discountAmount: 5, selectedPriceList: "",
        },
      ],
      customer: { id: "CUST-1" },
      customerData: customer,
      subtotal: 225,
      total: 261,
      taxAmount: 36,
      taxType: "exclusive",
      couponDiscount: 0,
      grandTotal: 261,
      appliedCoupons: [],
      itemDiscounts,
      totalItemDiscount: 20,
      totalSavings: 20,
      status: "held",
      businessType: "B2C",
      salesperson: "SP-1",
      selling_price_list: "Standard Selling",
      tax_id: null,
      walkin_name: null,
      walkin_phone: null,
      extra_fields: {},
      shipping_rule: null,
      deliveryCharge: 0,
      deliveryPersonnel: null,
      orderDiscountAmount: 0,
      SalesTaxCharges: "",
      remarks: "",
      loyalty: null,
    });
  });

  it("sends a redeemed loyalty program and points only", () => {
    const loyalty = { loyalty_program: "LP", loyalty_points: 10, amount: 100 };
    const payload = buildOrderPayload({
      cartItems: [],
      itemDiscounts: {},
      effectiveRate: () => 0,
      customer: { id: "C" },
      totals: { subtotal: 0, grandTotal: 0, taxAmount: 0, isInclusive: true, couponDiscount: 0 },
      appliedCoupons: [],
      businessType: undefined,
      salesperson: null,
      sellingPriceList: null,
      extras: { walkin: {}, extraFields: {}, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn },
      loyalty,
    });
    expect(payload.loyalty).toEqual({ loyalty_program: "LP", loyalty_points: 10 });
    expect(payload.taxType).toBe("inclusive");
  });
});

describe("custom-rate line", () => {
  it("sends only the cashier's discount, never the item's rule discount (it would come off the custom rate on recall)", () => {
    const payload = buildOrderPayload({
      cartItems: [{ id: "PEN", item_code: "PEN", quantity: 1, price: 10, discount_amount: 2 }],
      itemDiscounts: { PEN: { customRate: 8, discountAmount: 0 } },
      effectiveRate: () => 8,
      customer: { id: "C" },
      totals: { subtotal: 8, grandTotal: 8, taxAmount: 0, isInclusive: false, couponDiscount: 0 },
      appliedCoupons: [],
      businessType: "B2C",
      salesperson: null,
      sellingPriceList: null,
      extras: { walkin: {}, extraFields: {}, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn },
      loyalty: null,
    });
    expect(payload.items[0]!.discountAmount).toBe(0);
  });
});

describe("two lines of one item", () => {
  it("payload keeps each line's own discount, keyed by its line id", () => {
    const payload = buildOrderPayload({
      cartItems: [
        { id: "PEN", item_code: "PEN", quantity: 1, price: 10 },
        { id: "PEN-1731000000000", item_code: "PEN", quantity: 1, price: 10 },
      ],
      itemDiscounts: { PEN: { discountAmount: 1 }, "PEN-1731000000000": { discountAmount: 3 } },
      effectiveRate: () => 10,
      customer: { id: "C" },
      totals: { subtotal: 20, grandTotal: 20, taxAmount: 0, isInclusive: false, couponDiscount: 0 },
      appliedCoupons: [],
      businessType: "B2C",
      salesperson: null,
      sellingPriceList: null,
      extras: { walkin: {}, extraFields: {}, shippingRule: null, extras: EMPTY_CHECKOUT_EXTRAS, flags: allOn },
      loyalty: null,
    });
    expect(payload.items.map((i: { discountAmount: number }) => i.discountAmount)).toEqual([1, 3]);
    expect(payload.items.map((i: { id: string; line_id: string }) => [i.id, i.line_id])).toEqual([["PEN", "PEN"], ["PEN", "PEN-1731000000000"]]);
  });

  it("a held order with two PEN rows reloads as two lines with distinct ids", () => {
    const lines = heldItemsToCart([
      { item_code: "PEN", item_name: "Pen", quantity: 1, price: 10, uom: "Nos" },
      { item_code: "PEN", item_name: "Pen", quantity: 2, price: 8, uom: "Nos", discountAmount: 3 },
    ]);
    expect(lines.map((l) => l.item_code)).toEqual(["PEN", "PEN"]);
    expect(new Set(lines.map((l) => l.id)).size).toBe(2);
    expect(lines.map((l) => l.price)).toEqual([10, 8]);
    expect(lines.map((l) => l.discount_amount)).toEqual([0, 3]);
    expect(lines[0]!.id).toBe("PEN");
  });
});
