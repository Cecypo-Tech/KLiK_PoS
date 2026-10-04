// stores/cartStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { CartItem, GiftCoupon } from '../../types'
import type { Customer } from '../types/customer'
import { toast } from 'react-toastify'
import { clearDraftInvoiceCache } from '../utils/draftInvoiceCache'
import { clearCheckoutAttempt } from '../utils/checkoutAttempt'
import { usePOSProfileStore } from './posProfileStore'
import { roundCurrency } from '../utils/currencyMath'
import { applyLosAdjustments, losToast, planLineQty, type LosAdjustment } from '../utils/lossOfSale'
import { nextExpandedCartItemId } from '../utils/toggleItemExpansion'
import { consumeRateOverrides, enqueueRateOverride, type RateOverride } from '../utils/rateOverrides'
import { EMPTY_CHECKOUT_EXTRAS, type CheckoutExtras } from '../utils/heldOrderPayload'

interface SerialBatchEntry {
  serial_no?: string;
  batch_no?: string;
  qty?: number;
}

interface ItemTaxDetailsPayload {
  item_tax_template?: string;
  item_tax_rate?: Record<string, number>;
  rate?: number;
  tax_info?: {
    tax_templates?: Array<{ account: string; rate: number; is_inclusive: boolean }>;
    total_tax_rate?: number;
  };
}

interface PricedItemPayload {
  id?: string;
  item_code?: string;
  price?: number;
  original_price?: number;
  discount_percentage?: number;
  discount_amount?: number;
  pricing_rules?: unknown;
  has_pricing_rule?: boolean;
}

const roundToCurrencyPrecision = (value: number): number => {
  return roundCurrency(value);
};

const hasFiniteAvailableStock = (item: { available?: number; is_stock_item?: boolean; allow_negative_stock?: boolean }) => {
  if (item.is_stock_item === false || item.allow_negative_stock) {
    return false;
  }
  return typeof item.available === 'number' && Number.isFinite(item.available);
};

const losEnabledFor = (item: { has_serial_no?: boolean; is_product_bundle?: boolean }) =>
  !!usePOSProfileStore.getState().posDetails?.custom_enable_loss_of_sale &&
  !item.has_serial_no &&
  !item.is_product_bundle;

const sameItemQty = (items: CartItem[], code: string, exceptId?: string) =>
  items
    .filter((cartItem) => cartItem.id !== exceptId && (cartItem.item_code || cartItem.id) === code)
    .reduce((sum, cartItem) => sum + cartItem.quantity, 0);

const fetchItemTaxDetails = async (
  itemCode: string,
  customerId?: string,
  quantity: number = 1,
  uom?: string,
) => {
  try {
    const params = new URLSearchParams({
      item_code: itemCode,
      qty: String(quantity > 0 ? quantity : 1),
      uom: uom || 'Nos',
    });

    if (customerId) {
      params.append('customer', customerId);
    }

    const response = await fetch(
      `/api/method/klik_pos.api.item.item_tax_details.get_item_tax_details?${params.toString()}`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      },
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result = await response.json();
    const message: ItemTaxDetailsPayload & { success?: boolean } = result?.message || {};

    if (!message.success) {
      return {
        item_tax_template: '',
        item_tax_rate: {},
        rate: 0,
        tax_templates: [],
        total_tax_rate: 0,
      };
    }

    return {
      item_tax_template: message.item_tax_template || '',
      item_tax_rate: message.item_tax_rate || {},
      rate: roundToCurrencyPrecision(Number(message.rate || 0)),
      tax_templates: message.tax_info?.tax_templates || [],
      total_tax_rate: Number(message.tax_info?.total_tax_rate || 0),
    };
  } catch (error) {
    console.error('Error fetching item tax details:', error);
    return {
      item_tax_template: '',
      item_tax_rate: {},
      rate: 0,
      tax_templates: [],
      total_tax_rate: 0,
    };
  }
};

export interface WalkinDetails { name: string; taxId: string; phone: string }
const EMPTY_WALKIN: WalkinDetails = { name: '', taxId: '', phone: '' };

interface CartState {
  cartItems: CartItem[]
  appliedCoupons: GiftCoupon[]
  selectedCustomer: Customer | null
  walkinDetails: WalkinDetails
  extraFields: Record<string, string>
  highlightItemId: string | null
  highlightNonce: number
  selectedPriceList: string | null
  isPricingLoading: boolean
  pricingError: string | null

  addToCart: (item: Omit<CartItem, 'quantity'>) => Promise<void>
  addToCartQueued: (item: Omit<CartItem, 'quantity'>) => Promise<void>
  /** The cart line the quantity went to, or null when the cart refused it (stock). With
   * refresh false the caller refreshes pricing once after several adds. */
  addToCartWithQuantity: (
    item: Omit<CartItem, 'quantity'>,
    quantity: number,
    options?: { refresh?: boolean },
  ) => Promise<string | null>
  updateQuantity: (id: string, quantity: number) => Promise<void>
  adjustQuantity: (id: string, delta: number) => Promise<void>
  applyCheckoutLosAdjustments: (adjustments: LosAdjustment[]) => Promise<void>
  updateUOM: (id: string, uom: string, price: number, conversionFactor?: number) => Promise<void>
  removeItem: (id: string) => void
  clearCart: () => void
  applyCoupon: (coupon: GiftCoupon) => void
  removeCoupon: (couponCode: string) => void
  setSelectedCustomer: (customer: Customer | null) => Promise<void>
  setWalkinDetails: (details: Partial<WalkinDetails>) => void
  clearWalkinDetails: () => void
  setExtraFields: (v: Record<string, string>) => void
  clearExtraFields: () => void
  setSelectedPriceList: (priceList: string | null) => Promise<void>
  refreshCartPricing: () => Promise<void>
  updateItemBundleEntries: (id: string, entries: SerialBatchEntry[]) => void
  /** Shipping Rule chosen at checkout; its charge is added by the server. */
  shippingRule: string | null
  setShippingRule: (rule: string | null) => void
  /** Checkout state that must survive closing the dialog and a hold/recall: delivery
   * charge and person, order discount, tax template. Emptied with the cart. */
  checkoutExtras: CheckoutExtras
  setCheckoutExtras: (patch: Partial<CheckoutExtras>) => void
  updateItemDescription: (id: string, description: string) => void
  /** Which cart line's details panel is open. At most one at a time (opening a
   * second line closes the first). Deliberately not persisted: it's transient UI
   * state, not part of the cart itself. */
  expandedCartItemId: string | null
  toggleItemExpansion: (id: string) => void
  /** A rate-override request from outside the cart UI (the item list's '*'
   * shortcut). OrderSummary owns the actual rate/discount machinery
   * (itemDiscounts, checkout totals, persistence) and applies this via its
   * own existing handleCustomRateChange - this is a request to do that, not
   * a second place that sets a line's rate. Deliberately not persisted: a
   * leftover request must never replay after a reload. A queue, not one slot:
   * quick entry asks for several lines' rates at once, and a slot kept only the
   * last. nonce orders them and lets the same {itemId, rate} be asked twice.
   */
  pendingRateOverrides: RateOverride[]
  rateOverrideNonce: number
  requestCustomRate: (itemId: string, rate: number, includesTax?: boolean) => void
  /** Drop the requests up to and including `nonce`, once applied. */
  consumeRateOverrides: (nonce: number) => void
}

// Serializes rapid-fire adds (e.g. fast barcode scanning) so each add's
// read-modify-write of cartItems completes before the next one reads state -
// otherwise two adds started in parallel can both read the same starting
// quantity and one increment is lost.
let addQueue: Promise<unknown> = Promise.resolve();

const shouldInsertNewItemsAtTop = (): boolean => {
  const position = usePOSProfileStore.getState().posDetails?.custom_cart_item_insertion_position;
  return position === 'Top';
};

// Move the just-modified item to the configured insertion position (Top/Bottom)
// so a quantity bump from the product list lands where new items appear.
const reorderToInsertionPosition = (items: CartItem[], id: string): CartItem[] => {
  const idx = items.findIndex((i) => i.id === id);
  if (idx === -1) return items;
  const moved = items[idx];
  const rest = [...items.slice(0, idx), ...items.slice(idx + 1)];
  return shouldInsertNewItemsAtTop() ? [moved, ...rest] : [...rest, moved];
};

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      cartItems: [],
      appliedCoupons: [],
      selectedCustomer: null,
      walkinDetails: { name: '', taxId: '', phone: '' },
      extraFields: {},
      checkoutExtras: { ...EMPTY_CHECKOUT_EXTRAS },
      highlightItemId: null,
      highlightNonce: 0,
      selectedPriceList: null,
      isPricingLoading: false,
      pricingError: null,
      shippingRule: null,
      expandedCartItemId: null,
      toggleItemExpansion: (id) => set((s) => ({
        expandedCartItemId: nextExpandedCartItemId(s.expandedCartItemId, id),
      })),
      pendingRateOverrides: [],
      rateOverrideNonce: 0,
      requestCustomRate: (itemId, rate, includesTax = false) => set((s) => {
        const next = enqueueRateOverride(s.pendingRateOverrides, s.rateOverrideNonce, { itemId, rate, includesTax });
        return { pendingRateOverrides: next.queue, rateOverrideNonce: next.nonce };
      }),
      consumeRateOverrides: (nonce) => set((s) => ({
        pendingRateOverrides: consumeRateOverrides(s.pendingRateOverrides, nonce),
      })),

      refreshCartPricing: async () => {
        const state = get();
        if (state.cartItems.length === 0) return;

        set({ isPricingLoading: true, pricingError: null });

        try {
          const itemsForPricing = state.cartItems.map(item => ({
            id: item.id,
            item_code: item.item_code || item.id,
            quantity: item.quantity,
            price: item.price,
            uom: item.uom,
          }));

          const customerId = state.selectedCustomer?.id;
          const params = new URLSearchParams({
            cart_items: JSON.stringify(itemsForPricing),
          });
          if (customerId) params.append('customer', customerId);
          const allowPriceListSwitching = !!usePOSProfileStore.getState().posDetails?.allow_price_list_switching;
          if (allowPriceListSwitching && state.selectedPriceList) params.append('price_list', state.selectedPriceList);
          const url = `/api/method/klik_pos.api.item.pricing.get_cart_pricing?${params.toString()}`;
          
          const response = await fetch(url, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const result = await response.json();
          const pricingData = result.message;

          if (pricingData?.items) {
            set((state) => ({
              cartItems: state.cartItems.map(item => {
                const pricedItem = (pricingData.items as PricedItemPayload[]).find((p) => 
                  (p.id === item.id) || (p.item_code === (item.item_code || item.id))
                );
                if (pricedItem) {
                  const basePrice = Number(pricedItem.price || 0);

                  return {
                    ...item,
                    price: roundToCurrencyPrecision(basePrice),
                    original_price: pricedItem.original_price,
                    discount_percentage: pricedItem.discount_percentage,
                    discount_amount: pricedItem.discount_amount,
                    pricing_rules: pricedItem.pricing_rules,
                    has_pricing_rule: pricedItem.has_pricing_rule,
                  };
                }
                return item;
              }),
              isPricingLoading: false,
            }));
          } else {
            set({ isPricingLoading: false });
          }
        } catch (error) {
          console.error('Error refreshing cart pricing:', error);
          set({ 
            pricingError: error instanceof Error ? error.message : 'Failed to update prices',
            isPricingLoading: false 
          });
        }
      },

      addToCart: async (item) => {
        const state = get();
        const incomingCode = item.item_code || item.id;
        const customerId = state.selectedCustomer?.id;
        const existingItem = state.cartItems.find((cartItem) =>
          cartItem.id === item.id || (cartItem.item_code || cartItem.id) === incomingCode
        );
        const totalMatchingQty = state.cartItems
          .filter((cartItem) => (cartItem.item_code || cartItem.id) === incomingCode)
          .reduce((sum, cartItem) => sum + cartItem.quantity, 0);

        const limited = hasFiniteAvailableStock(item);
        const losEnabled = losEnabledFor(item);
        if (limited && item.available <= 0 && !losEnabled) {
          toast.error(`${item.name} is out of stock`);
          return;
        }

        if (existingItem) {
          const plan = planLineQty({
            limited,
            available: item.available ?? 0,
            requested: existingItem.quantity + (existingItem.los_qty ?? 0) + 1,
            otherLinesQty: totalMatchingQty - existingItem.quantity,
            losEnabled,
          });
          if (!plan) {
            toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
            return;
          }
          if (plan.los_qty > (existingItem.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

          const targetId = existingItem.id;
          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            plan.quantity || 1,
            existingItem.uom || item.uom,
          );

          set((state) => {
            const updated = state.cartItems.map((cartItem) =>
              cartItem.id === targetId
                ? {
                    ...cartItem,
                    quantity: plan.quantity,
                    los_qty: plan.los_qty,
                    item_tax_template: taxDetails.item_tax_template,
                    item_tax_rate: taxDetails.item_tax_rate,
                    tax_templates: taxDetails.tax_templates,
                    total_tax_rate: taxDetails.total_tax_rate,
                  }
                : cartItem
            );
            return {
              cartItems: reorderToInsertionPosition(updated, targetId),
              highlightItemId: targetId,
              highlightNonce: state.highlightNonce + 1,
            };
          });
        } else {
          const plan = planLineQty({
            limited,
            available: item.available ?? 0,
            requested: 1,
            otherLinesQty: totalMatchingQty,
            losEnabled,
          });
          if (!plan) return;
          if (plan.los_qty > 0) toast.warning(losToast(item.name, item.uom, plan));

          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            1,
            item.uom,
          );

          const newItem = {
            ...item,
            quantity: plan.quantity,
            los_qty: plan.los_qty,
            bundle_entries: [],
            item_tax_template: taxDetails.item_tax_template,
            item_tax_rate: taxDetails.item_tax_rate,
            tax_templates: taxDetails.tax_templates,
            total_tax_rate: taxDetails.total_tax_rate,
          };
          const newCartItems = shouldInsertNewItemsAtTop()
            ? [newItem, ...state.cartItems]
            : [...state.cartItems, newItem];
          set((s) => ({
            cartItems: newCartItems,
            highlightItemId: newItem.id,
            highlightNonce: s.highlightNonce + 1,
          }));
        }

        await get().refreshCartPricing();
      },

      addToCartQueued: (item) => {
        const run = addQueue
          .then(() => get().addToCart(item))
          .catch((error) => {
            console.error('Queued add to cart failed:', error);
          });
        addQueue = run;
        return run;
      },

      addToCartWithQuantity: async (item, quantity, options) => {
        const state = get();
        const incomingCode = item.item_code || item.id;
        const customerId = state.selectedCustomer?.id;
        const existingItem = state.cartItems.find((cartItem) =>
          cartItem.id === item.id || (cartItem.item_code || cartItem.id) === incomingCode
        );
        const totalMatchingQty = state.cartItems
          .filter((cartItem) => (cartItem.item_code || cartItem.id) === incomingCode)
          .reduce((sum, cartItem) => sum + cartItem.quantity, 0);

        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested: existingItem ? existingItem.quantity + (existingItem.los_qty ?? 0) + quantity : quantity,
          otherLinesQty: totalMatchingQty - (existingItem?.quantity ?? 0),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
          return null;
        }
        if (plan.los_qty > (existingItem?.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

        let lineId: string;
        if (existingItem) {
          const targetId = existingItem.id;
          lineId = targetId;
          const updatedQty = plan.quantity;
          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            updatedQty || 1,
            existingItem.uom || item.uom,
          );

          set((state) => {
            const updated = state.cartItems.map((cartItem) =>
              cartItem.id === targetId
                ? {
                    ...cartItem,
                    quantity: updatedQty,
                    los_qty: plan.los_qty,
                    item_tax_template: taxDetails.item_tax_template,
                    item_tax_rate: taxDetails.item_tax_rate,
                    tax_templates: taxDetails.tax_templates,
                    total_tax_rate: taxDetails.total_tax_rate,
                  }
                : cartItem
            );
            return {
              cartItems: reorderToInsertionPosition(updated, targetId),
              highlightItemId: targetId,
              highlightNonce: state.highlightNonce + 1,
            };
          });
        } else {
          const taxDetails = await fetchItemTaxDetails(
            incomingCode,
            customerId,
            plan.quantity || 1,
            item.uom,
          );

          const newItem = {
            ...item,
            quantity: plan.quantity,
            los_qty: plan.los_qty,
            bundle_entries: [],
            item_tax_template: taxDetails.item_tax_template,
            item_tax_rate: taxDetails.item_tax_rate,
            tax_templates: taxDetails.tax_templates,
            total_tax_rate: taxDetails.total_tax_rate,
          };
          const newCartItems = shouldInsertNewItemsAtTop()
            ? [newItem, ...state.cartItems]
            : [...state.cartItems, newItem];
          lineId = newItem.id;
          set((s) => ({
            cartItems: newCartItems,
            highlightItemId: newItem.id,
            highlightNonce: s.highlightNonce + 1,
          }));
        }

        if (options?.refresh !== false) await get().refreshCartPricing();
        return lineId;
      },

      updateQuantity: async (id, quantity) => {
        const state = get();
        if (quantity <= 0) {
          set({
            cartItems: state.cartItems.filter((item) => item.id !== id)
          });
          await get().refreshCartPricing();
          return;
        }

        const item = state.cartItems.find((cartItem) => cartItem.id === id);
        if (!item) return;
        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested: quantity,
          otherLinesQty: sameItemQty(state.cartItems, item.item_code || item.id, id),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.error(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available`);
          return;
        }
        if (plan.los_qty > (item.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

        set({
          cartItems: state.cartItems.map((cartItem) =>
            cartItem.id === id ? { ...cartItem, quantity: plan.quantity, los_qty: plan.los_qty } : cartItem
          )
        });

        await get().refreshCartPricing();
      },

      // Delta-based stepper action. Reads the current quantity fresh from the
      // store at call time instead of trusting a value computed from a React
      // prop, so rapid back-to-back clicks (which fire before the row
      // re-renders) each apply correctly instead of collapsing into one.
      adjustQuantity: async (id, delta) => {
        const state = get();
        const item = state.cartItems.find((cartItem) => cartItem.id === id);
        if (!item) return;

        const requested = item.quantity + (item.los_qty ?? 0) + delta;

        if (requested <= 0) {
          get().removeItem(id);
          return;
        }

        const plan = planLineQty({
          limited: hasFiniteAvailableStock(item),
          available: item.available ?? 0,
          requested,
          otherLinesQty: sameItemQty(state.cartItems, item.item_code || item.id, id),
          losEnabled: losEnabledFor(item),
        });
        if (!plan) {
          toast.warning(`Only ${item.available} ${item.uom || 'units'} of ${item.name} available.`);
          return;
        }
        if (plan.los_qty > (item.los_qty ?? 0)) toast.warning(losToast(item.name, item.uom, plan));

        set((s) => ({
          cartItems: s.cartItems.map((cartItem) =>
            cartItem.id === id ? { ...cartItem, quantity: plan.quantity, los_qty: plan.los_qty } : cartItem
          ),
          highlightItemId: id,
          highlightNonce: s.highlightNonce + 1,
        }));

        await get().refreshCartPricing();
      },

      applyCheckoutLosAdjustments: async (adjustments) => {
        if (!adjustments?.length) return;
        set((s) => ({ cartItems: applyLosAdjustments(s.cartItems, adjustments) }));
        toast.warning(
          adjustments.length === 1
            ? `Stock changed: 1 line shortened, the rest recorded as Loss of Sale`
            : `Stock changed: ${adjustments.length} lines shortened, the rest recorded as Loss of Sale`,
        );
        await get().refreshCartPricing();
      },

      updateUOM: async (id, uom, price, conversionFactor) => {
        set((state) => ({
          cartItems: state.cartItems.map((item) => {
            if (item.id === id) {
              // The factor turns this UOM into stock units, which the net weight needs.
              return conversionFactor
                ? { ...item, uom, price, conversion_factor: conversionFactor }
                : { ...item, uom, price };
            }
            return item;
          })
        }));
        await get().refreshCartPricing();
      },

      removeItem: (id) => {
        set((state) => ({
          cartItems: state.cartItems.filter((item) => item.id !== id),
          // A removed line's id can be reused by a later add (addToCart takes it
          // straight off the item), so a stale expanded id left pointing at it
          // would silently attach to whatever line lands on that id next.
          expandedCartItemId: state.expandedCartItemId === id ? null : state.expandedCartItemId,
        }));
        get().refreshCartPricing();
      },

      clearCart: () => {
        clearDraftInvoiceCache();
        // The cart is gone, so the idempotency key that described it is spent.
        clearCheckoutAttempt();
        set(() => ({
          cartItems: [],
          appliedCoupons: [],
          selectedCustomer: null,
          walkinDetails: { ...EMPTY_WALKIN },
          extraFields: {},
          selectedPriceList: null,
          shippingRule: null,
          checkoutExtras: { ...EMPTY_CHECKOUT_EXTRAS },
          expandedCartItemId: null,
        }));
      },

      applyCoupon: (coupon) => set((state) => {
        if (!state.appliedCoupons.some((c) => c.code === coupon.code)) {
          return {
            appliedCoupons: [...state.appliedCoupons, coupon]
          }
        }
        return state
      }),

      removeCoupon: (couponCode) => set((state) => ({
        appliedCoupons: state.appliedCoupons.filter((coupon) => coupon.code !== couponCode)
      })),

      setSelectedCustomer: async (customer) => {
        set({ selectedCustomer: customer });
        if (!customer || customer.isWalkin !== 1) {
          set({ walkinDetails: { ...EMPTY_WALKIN } });
        }
        const state = get();
        if (state.cartItems.length > 0) {
          await state.refreshCartPricing();
        }
      },

      setWalkinDetails: (details) =>
        set((s) => ({ walkinDetails: { ...s.walkinDetails, ...details } })),
      clearWalkinDetails: () => set({ walkinDetails: { ...EMPTY_WALKIN } }),
      setExtraFields: (v) => set({ extraFields: v }),
      clearExtraFields: () => set({ extraFields: {} }),
      setShippingRule: (rule) => set({ shippingRule: rule || null }),
      setCheckoutExtras: (patch) => set((s) => ({ checkoutExtras: { ...s.checkoutExtras, ...patch } })),
      updateItemDescription: (id, description) =>
        set((state) => ({
          cartItems: state.cartItems.map((item) =>
            item.id === id ? { ...item, description } : item
          ),
        })),

      setSelectedPriceList: async (priceList) => {
        set({ selectedPriceList: priceList });
        const state = get();
        if (state.cartItems.length > 0) {
          await state.refreshCartPricing();
        }
      },

      updateItemBundleEntries: (id: string, entries: SerialBatchEntry[]) => {
        set((state) => ({
          cartItems: state.cartItems.map((item) =>
            item.id === id
              ? { ...item, bundle_entries: entries }
              : item
          )
        }));
      },
    }),
    {
      name: 'beveren-cart-storage',
      // expandedCartItemId is transient UI state, not cart data - and a stale
      // expanded row reappearing after a reload would be surprising.
      partialize: (state) => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { expandedCartItemId, pendingRateOverrides, rateOverrideNonce, ...rest } = state;
        return rest;
      },
    }
  )
)
