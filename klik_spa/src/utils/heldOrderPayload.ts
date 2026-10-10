import type { CartItem } from '../../types';
/**
 * Everything a held order must carry besides its lines, and how it comes back.
 *
 * The cart's Hold button used to send only the items: the walk-in buyer, the till's extra
 * fields (whatever the POS Profile lists - PO number and the like), the shipping rule and the
 * checkout's delivery charge, delivery person, order discount and tax template were all lost,
 * so held orders could not be told apart or resumed as they were. Checkout's own Hold sent
 * most of them, but not the delivery person, and resuming restored none of the checkout's.
 *
 * Both Hold buttons build these keys here, from the cart store; resuming maps them back.
 * The till's switches apply both ways: a till that does not allow a delivery charge, a
 * shipping rule or a discount change neither sends nor restores one.
 */

export interface CheckoutExtras {
  deliveryCharge: number;
  deliveryPersonnel: string | null;
  orderDiscountAmount: number;
  /** Sales Taxes and Charges Template chosen at checkout; "" means the till's default. */
  salesTaxCharges: string;
  /** The cashier's note, kept on the held order and written to the invoice's Remarks. */
  remarks: string;
}

export const EMPTY_CHECKOUT_EXTRAS: CheckoutExtras = {
  deliveryCharge: 0,
  deliveryPersonnel: null,
  orderDiscountAmount: 0,
  salesTaxCharges: "",
  remarks: "",
};

export interface TillFlags {
  deliveryCharge: boolean;
  shippingRule: boolean;
  discountChange: boolean;
}

const on = (value: unknown) => value === 1 || value === "1" || value === true;

export function tillFlags(posDetails: Record<string, unknown> | null | undefined): TillFlags {
  return {
    deliveryCharge: on(posDetails?.custom_enable_delivery_charge),
    shippingRule: on(posDetails?.custom_enable_shipping_rule),
    discountChange: on(posDetails?.allow_discount_change),
  };
}

const clean = (value?: string | null) => (value ?? "").trim() || null;
const money = (value: unknown) => Math.max(0, Number(value) || 0);

export function heldOrderPayloadExtras({
  walkin,
  extraFields,
  shippingRule,
  extras,
  flags,
}: {
  walkin: { name?: string; taxId?: string; phone?: string };
  extraFields: Record<string, string> | undefined;
  shippingRule: string | null;
  extras: CheckoutExtras;
  flags: TillFlags;
}) {
  const rule = flags.shippingRule ? clean(shippingRule) : null;
  return {
    tax_id: clean(walkin.taxId),
    walkin_name: clean(walkin.name),
    walkin_phone: clean(walkin.phone),
    extra_fields: extraFields ?? {},
    shipping_rule: rule,
    // The server refuses a delivery charge on a till without the switch, and refuses one
    // beside a shipping rule - delivery would be paid twice.
    deliveryCharge: flags.deliveryCharge && !rule ? money(extras.deliveryCharge) : 0,
    deliveryPersonnel: clean(extras.deliveryPersonnel),
    orderDiscountAmount: money(extras.orderDiscountAmount),
    SalesTaxCharges: extras.salesTaxCharges || "",
    // Always sent: holding again with the box emptied clears the order's remarks.
    remarks: (extras.remarks || "").trim(),
  };
}

export function checkoutExtrasFromHeldOrder(
  details: { discount_amount?: number; remarks?: string | null; cart_meta?: Record<string, unknown> | null },
  flags: TillFlags,
): CheckoutExtras {
  const meta = details.cart_meta ?? {};
  return {
    deliveryCharge: flags.deliveryCharge ? money(meta.deliveryCharge) : 0,
    deliveryPersonnel: clean(meta.deliveryPersonnel as string | null | undefined),
    orderDiscountAmount: flags.discountChange ? money(details.discount_amount) : 0,
    salesTaxCharges: typeof meta.SalesTaxCharges === "string" ? meta.SalesTaxCharges : "",
    // The order's own field wins - even emptied in desk; the cart copy only for an older server.
    remarks: typeof details.remarks === "string" ? details.remarks : typeof meta.remarks === "string" ? meta.remarks : "",
  };
}

/** A held order's line as the cart holds it, its Loss of Sale split included. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function heldItemToCartItem(item: any): CartItem {
  return {
    id: item.item_code,
    item_code: item.item_code,
    name: item.item_name,
    category: '',
    price: item.price,
    original_price: item.price,
    quantity: item.quantity,
    los_qty: Number(item.los_qty) || 0,
    uom: item.uom || 'Nos',
    bundle_entries: item.bundle_entries || [],
    // Persist discount fields so OrderSummary can restore itemDiscounts state
    discount_amount: item.discountAmount || 0,
    discount_percentage: item.discountPercentage || 0,
    custom_rate: item.customRate ?? undefined,
    custom_rate_includes_tax: item.customRateIncludesTax ?? undefined,
    item_tax_template: item.item_tax_template || '',
    item_tax_rate: item.item_tax_rate || {},
    description: item.description || '',
  } as unknown as CartItem;
}
