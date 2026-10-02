import { getHeldOrderDetails } from '../services/salesOrder';
import { cacheHeldOrder, loadCachedItemsToCart } from './draftInvoiceCache';
import { transformCustomerInfo } from './transformCustomerInfo';
import { useCartStore } from '../stores/cartStore';
import { usePOSProfileStore } from '../stores/posProfileStore';
import { checkoutExtrasFromHeldOrder, tillFlags } from './heldOrderPayload';
import type { CartItem, Customer } from '../../types';

// transformCustomerInfo returns the `types/customer` Customer; the cache stores the
// `types/index` Customer. They are structurally compatible at runtime — bridge here.
type CacheCustomer = Customer;

export async function addHeldOrderToCart(orderId: string): Promise<boolean> {
  const orderData = await getHeldOrderDetails(orderId);
  if (!orderData?.success) {
    throw new Error(orderData?.message || 'Failed to load held order');
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const items: CartItem[] = orderData.items.map((item: any) => ({
    id: item.item_code,
    item_code: item.item_code,
    name: item.item_name,
    category: '',
    price: item.price,
    original_price: item.price,
    quantity: item.quantity,
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
  } as unknown as CartItem));

  // Resolve customer object — must be a full Customer (with `id`) so checkout can
  // send customer.id, matching the customer-search selection flow.
  let customer: CacheCustomer | null = null;

  // Fast path: the full customer object was persisted in cart_meta at hold time.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (orderData.customer_data && (orderData.customer_data as any).id) {
    customer = orderData.customer_data as unknown as CacheCustomer;
  } else if (orderData.customer) {
    // Fallback (older held orders): re-fetch and transform by customer id.
    try {
      const res = await fetch(
        `/api/method/klik_pos.api.customer.get_customer_info?customer_name=${encodeURIComponent(orderData.customer)}`,
        { credentials: 'include' },
      );
      const data = await res.json();
      const raw = data?.message;
      if (raw && raw.name && raw.success !== false) {
        customer = transformCustomerInfo(raw) as unknown as CacheCustomer;
      }
    } catch {
      // non-fatal — cart will load without a resolved customer object
    }
  }

  cacheHeldOrder(
    orderId,
    items,
    customer,
    Number(orderData.discount_amount) || 0,
    {
      state: orderData.approval_state ?? null,
      priceBreach: Number(orderData.price_breach) || 0,
    },
    { isMpesaOrder: Boolean(orderData.mpesa_order), request: orderData.mpesa_request ?? null },
  );

  // Restore per-transaction walk-in details (name/tax_id/phone) into the cart store.
  // Also recovers tax_id, which was previously dropped from the UI on resume.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const od = orderData as any;
  useCartStore.getState().setWalkinDetails({
    name: od.walkin_name || '',
    taxId: od.cart_meta?.tax_id || od.tax_id || '',
    phone: od.walkin_phone || '',
  });

  useCartStore.getState().setExtraFields(od.extra_fields || od.cart_meta?.extra_fields || {});
  // The till's switches decide what comes back: a rule, charge or discount it no longer
  // allows would only get the next hold or checkout refused.
  const flags = tillFlags(usePOSProfileStore.getState().posDetails as Record<string, unknown> | null);
  useCartStore.getState().setShippingRule(
    flags.shippingRule ? (od.shipping_rule || od.cart_meta?.shipping_rule || null) : null,
  );
  useCartStore.getState().setCheckoutExtras(checkoutExtrasFromHeldOrder(od, flags));

  return loadCachedItemsToCart();
}
