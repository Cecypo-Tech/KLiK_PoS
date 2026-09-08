import { useCartStore } from '../stores/cartStore';
import type { CartItem, Customer } from '../../types';

interface DraftInvoiceCache {
  items: CartItem[];
  timestamp: number;
  invoiceId: string;
  customer: Customer | null;
  originalDraftInvoiceId: string; // draft SI (M-Pesa / legacy held)
  originalHeldOrderId?: string;   // SO-based held order
  orderDiscountAmount?: number;   // additional discount amount carried over from hold/draft
}

const CACHE_KEY = 'draft-invoice-cache';

/**
 * How long a cached *cart* may be restored for. A cart abandoned half an hour ago should
 * not reappear under someone else's sale, so restoring items stays on a timer.
 */
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

export function cacheDraftInvoiceItems(
  invoiceId: string,
  items: CartItem[],
  customer: Customer | null,
  orderDiscountAmount = 0,
): void {
  const cache: DraftInvoiceCache = {
    items,
    timestamp: Date.now(),
    invoiceId,
    customer,
    originalDraftInvoiceId: invoiceId,
    orderDiscountAmount,
  };

  localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

export function cacheHeldOrder(
  orderId: string,
  items: CartItem[],
  customer: Customer | null,
  orderDiscountAmount = 0,
): void {
  const cache: DraftInvoiceCache = {
    items,
    timestamp: Date.now(),
    invoiceId: orderId,
    customer,
    originalDraftInvoiceId: '',
    originalHeldOrderId: orderId,
    orderDiscountAmount,
  };
  localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

/**
 * Which document this cart is editing, regardless of how long the edit has taken.
 *
 * The identity deliberately does NOT expire. It used to be read through the five-minute
 * items cache, so recalling a held order, serving somebody else, and holding it again
 * twenty minutes later sent no held_order_id at all - and the server, asked to hold an
 * order it had never seen, inserted a second Sales Order and left the first one held. The
 * duplicate only appeared when the edit ran long, which is why it looked intermittent.
 *
 * The link dies with the cart, not with a stopwatch: clearCart, checkout and hold all call
 * clearDraftInvoiceCache.
 */
function readCacheIgnoringAge(): DraftInvoiceCache | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;
    return JSON.parse(cached) as DraftInvoiceCache;
  } catch {
    return null;
  }
}

export function getCachedDraftInvoiceItems(): DraftInvoiceCache | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);

    if (!cached) {
      return null;
    }

    const cache: DraftInvoiceCache = JSON.parse(cached);

    const now = Date.now();
    const age = now - cache.timestamp;

    if (age > CACHE_DURATION) {
      clearDraftInvoiceCache();
      return null;
    }

    return cache;
  } catch (error) {
    console.error('Error retrieving cached draft invoice items:', error);
    clearDraftInvoiceCache();
    return null;
  }
}

export function clearDraftInvoiceCache(): void {
  localStorage.removeItem(CACHE_KEY);
}

export async function loadCachedItemsToCart(): Promise<boolean> {
  const cachedData = getCachedDraftInvoiceItems();
  if (!cachedData || cachedData.items.length === 0) {
    return false;
  }

  const mappedItems = cachedData.items.map((item) => ({
    ...item,
    item_code: item.item_code || item.id,
    quantity: item.quantity,
    bundle_entries: item.bundle_entries || [],
  }));

  useCartStore.setState((state) => ({
    ...state,
    cartItems: mappedItems,
    appliedCoupons: [],
    selectedCustomer: cachedData.customer,
  }));

  return true;
}

export function hasCachedDraftInvoiceItems(): boolean {
  const cached = localStorage.getItem(CACHE_KEY);

  if (!cached) {
    return false;
  }

  try {
    const cache: DraftInvoiceCache = JSON.parse(cached);
    const isValid = Date.now() - cache.timestamp <= CACHE_DURATION;
    return isValid;
  } catch (error) {
    console.error('Error checking cache validity:', error);
    return false;
  }
}

export function getOriginalDraftInvoiceId(): string | null {
  return readCacheIgnoringAge()?.originalDraftInvoiceId || null;
}

export function getOriginalHeldOrderId(): string | null {
  return readCacheIgnoringAge()?.originalHeldOrderId || null;
}

export function getOriginalOrderDiscountAmount(): number {
  return readCacheIgnoringAge()?.orderDiscountAmount || 0;
}
