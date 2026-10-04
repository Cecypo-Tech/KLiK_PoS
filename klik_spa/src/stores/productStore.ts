import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'react-toastify';
import type { MenuItem, Customer, ItemGroup } from '../../types';
import { usePOSProfileStore } from './posProfileStore';
import { useCartStore } from './cartStore';
import { applyStockUpdates, chunkCodes, stockRefreshCodes } from '../utils/stockRefresh';
import { getCSRFToken } from '../utils/csrf';
import { filterAvailableProducts } from '../utils/productFilter';
import { resolveNextOffset } from '../utils/pagination';
import { expandTaxProfiles } from '../utils/productPayload';
import { createKeyedDedupe, firstPageKey, listingIncludesGroups, pageAdvanced, SEARCH_PAGE_SIZE, type PageCursor } from '../utils/productLoading';

interface ProductStoreState {
  products: MenuItem[];
  /** What the category bar shows: the till's groups, or a search's narrowed counts. */
  itemGroups: ItemGroup[];
  /** The till's groups without any search - kept between visits. */
  baseItemGroups: ItemGroup[];
  customers: Customer[];
  selectedCustomer: Customer | null;
  searchQuery: string;
  selectedCategory: string;
  totalCount: number;
  hasMore: boolean;
  currentOffset: number;
  currentCursor: PageCursor | null;
  isLoading: boolean;
  isLoadingMore: boolean;
  isSearching: boolean;
  isLoadingCustomers: boolean;
  isRefreshingStock: boolean;
  error: string | null;
  lastFullRefresh: number | null;
  lastUpdated: Date | null;
  isInitialized: boolean;
  // Set from the backend's degradation contract (same keys as api/receivables.py). A
  // permission gap degrades rather than erroring, so this is the only way the UI learns
  // that what it is showing is incomplete.
  degraded: boolean;
  degradedReason: string | null;
  stockUnavailable: boolean;
  posName: string | null;
  initializePOS: (posName: string, customerId?: string) => Promise<void>;
  fetchProducts: (reset?: boolean) => Promise<void>;
  loadMoreProducts: () => Promise<void>;
  searchProducts: (query: string, immediate?: boolean) => Promise<void>;
  resolveSearchNow: () => Promise<void>;
  clearSearch: () => void;
  setCategory: (category: string) => void;
  refreshStockOnly: () => Promise<boolean>;
  refreshStockNow: () => Promise<boolean>;
  updateStockOnly: (itemCode: string, newStock: number) => void;
  updateStockForItems: (itemCodes: string[]) => Promise<void>;
  searchCustomers: (query: string) => Promise<Customer[]>;
  setSelectedCustomer: (customer: Customer | null) => void;
  clearCache: () => void;
  fetchItemGroups: () => Promise<void>;
  stopBackgroundRefresh: () => void;
  startBackgroundRefresh: () => void;
  executeSearch: (query: string) => Promise<void>;
  attemptIdentifierLookup: (query: string) => Promise<boolean>;
  fetchItemByIdentifier: (code: string) => Promise<MenuItem | null>;
  fetchProductsFromAPI: (
    limit: number,
    offset: number,
    search: string,
    category: string,
    customerId: string,
    priceList?: string,
    options?: { cursor?: PageCursor | null; includeCount?: boolean },
  ) => Promise<{
    items: MenuItem[];
    item_groups: ItemGroup[];
    total_count: number | null;
    page_count: number;
    has_more: boolean;
    next_offset: number | null;
    next_cursor: PageCursor | null;
    degraded: boolean;
    degraded_reason: string | null;
    stock_unavailable: boolean;
  }>;
  fetchStockUpdates: () => Promise<Record<string, number>>;
  getFilteredItems: () => MenuItem[];
  getUseScannerOnly: () => boolean;
  getHideUnavailableItems: () => boolean;
  getScalePrefix: () => string;
  getDefaultView: () => 'grid' | 'list';
  checkAndInitialize: () => void;
  syncCustomerFromCart: () => void;
  getEffectiveCustomer: () => Customer | null;
  getEffectivePriceList: () => string;
}

const PAGE_SIZE = 250;
const LOAD_MORE_SIZE = 150;
const CACHE_DURATION = 5 * 60 * 1000;
const STOCK_REFRESH_CHUNK = 200;
let currentPosName = '';
let refreshTimers: Array<ReturnType<typeof setInterval>> = [];
let searchTimer: ReturnType<typeof setTimeout> | null = null;
let identifierTimer: ReturnType<typeof setTimeout> | null = null;
const IDENTIFIER_LIKE_PATTERN = /^\S{6,}$/;

type FirstPage = Awaited<ReturnType<ProductStoreState['fetchProductsFromAPI']>>;
// Startup has several triggers (profile load, customer sync, price list); overlapping
// loads of the same first page share one request.
const dedupeFirstPage = createKeyedDedupe<FirstPage>();

/** POST so a long list of item codes never outgrows a URL. */
async function fetchStockFor(codes: string[]): Promise<Record<string, number>> {
  const merged: Record<string, number> = {};
  for (const chunk of chunkCodes(codes, STOCK_REFRESH_CHUNK)) {
    try {
      const response = await fetch('/api/method/klik_pos.api.item.item_stock.get_items_stock_batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': getCSRFToken() ?? '' },
        credentials: 'include',
        body: JSON.stringify({ item_codes: chunk.join(','), warehouse: usePOSProfileStore.getState().warehouse || undefined }),
      });
      if (response.ok) {
        const data = await response.json();
        Object.assign(merged, data?.message || {});
      }
    } catch (error) {
      console.error('Stock update failed:', error);
    }
  }
  return merged;
}

// Refreshes run one at a time; a call that arrives meanwhile shares one follow-up run (so the
// post-sale refresh is never lost) and resolves after it.
let stockRefreshRun: Promise<boolean> | null = null;
let stockRefreshQueued: Promise<boolean> | null = null;

export const useProductStore = create<ProductStoreState>()(
  persist(
    (set, get) => ({
      products: [],
      itemGroups: [],
      baseItemGroups: [],
      customers: [],
      selectedCustomer: null,
      searchQuery: '',
      selectedCategory: 'all',
      totalCount: 0,
      hasMore: false,
      degraded: false,
      degradedReason: null,
      stockUnavailable: false,
      currentOffset: 0,
      currentCursor: null,
      isLoading: false,
      isLoadingMore: false,
      isSearching: false,
      isLoadingCustomers: false,
      isRefreshingStock: false,
      error: null,
      lastFullRefresh: null,
      lastUpdated: null,
      isInitialized: false,
      posName: null,

      getFilteredItems: () =>
        filterAvailableProducts(get().products, usePOSProfileStore.getState().hideUnavailableItems),
      
      getUseScannerOnly: () => usePOSProfileStore.getState().useScannerOnly,
      getHideUnavailableItems: () => usePOSProfileStore.getState().hideUnavailableItems,
      getScalePrefix: () => usePOSProfileStore.getState().scalePrefix,
      getDefaultView: () => usePOSProfileStore.getState().defaultView,

      getEffectiveCustomer: () => {
        const cartCustomer = useCartStore.getState().selectedCustomer;
        const { selectedCustomer } = get();
        
        if (cartCustomer) {
          return cartCustomer;
        }
        return selectedCustomer;
      },

      getEffectivePriceList: () => {
        const allowPriceListSwitching = !!usePOSProfileStore.getState().posDetails?.allow_price_list_switching;
        const cartState = useCartStore.getState();
        return (allowPriceListSwitching ? cartState.selectedPriceList : null)
          || cartState.selectedCustomer?.sellingPriceList
          || get().selectedCustomer?.sellingPriceList
          || "";
      },

      syncCustomerFromCart: () => {
        const cartCustomer = useCartStore.getState().selectedCustomer;
        const { selectedCustomer } = get();
        
        if (cartCustomer && (!selectedCustomer || selectedCustomer.id !== cartCustomer.id)) {
          set({ selectedCustomer: cartCustomer });
          if (currentPosName) {
            get().initializePOS(currentPosName, cartCustomer.id);
          }
        }
      },

      checkAndInitialize: () => {
        const { posName, isInitialized, isLoading } = get();
        const profileStore = usePOSProfileStore.getState();
        
        get().syncCustomerFromCart();
        
        if (!posName && profileStore.isInitialized && profileStore.posDetails?.name) {
          const profileName = profileStore.posDetails.name;
          set({ posName: profileName });
          get().initializePOS(profileName);
        } else if (posName && !isInitialized && !isLoading) {
          get().initializePOS(posName);
        }
      },

      fetchProductsFromAPI: async (limit, offset, search, category, customerId, priceList, options) => {
        try {
          const params = new URLSearchParams({
            limit: limit.toString(),
            offset: offset.toString(),
            pos_profile: currentPosName,
          });
          
          if (customerId) {
            params.append('customer', customerId);
          }
          
          if (priceList) {
            params.append('price_list', priceList);
          }

          const selectedWarehouse = usePOSProfileStore.getState().warehouse;
          if (selectedWarehouse) {
            params.append('warehouse', selectedWarehouse);
          }

          if (search) params.append('search', search);
          if (category && category !== 'all') params.append('category', category);
          // The bar's groups load on their own (fetchItemGroups); the listing sends them
          // only while a search narrows their counts.
          params.append('include_groups', listingIncludesGroups(search || '') ? '1' : '0');
          params.append('compact_tax', '1');
          // Later pages skip the count (the till keeps the first page's) and continue
          // after the previous page's last row.
          if (options?.includeCount === false) params.append('include_count', '0');
          if (options?.cursor) {
            params.append('after_name', options.cursor.after_name);
            params.append('after_code', options.cursor.after_code);
          }

          const response = await fetch(`/api/method/klik_pos.api.item.item_listing.get_items?${params.toString()}`);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          
          const data = await response.json();
          const message = data?.message || data;
          
          return {
            items: expandTaxProfiles(message.items || [], message.tax_profiles),
            item_groups: message.item_groups || [],
            total_count: typeof message.total_count === 'number' ? message.total_count : null,
            page_count: message.page_count ?? (message.items || []).length,
            has_more: message.has_more || false,
            // Advances by SQL rows consumed, which is not the same as items received once
            // hide_unavailable_items filters a page. null on an older backend that does
            // not send it - callers fall back to counting items.
            next_offset: typeof message.next_offset === 'number' ? message.next_offset : null,
            next_cursor: message.next_cursor ?? null,
            degraded: !!message.degraded,
            degraded_reason: message.degraded_reason ?? null,
            stock_unavailable: !!message.stock_unavailable,
          };
        } catch (err) {
          console.error('fetchProductsFromAPI error:', err);
          return {
            items: [], item_groups: [], total_count: null, page_count: 0, has_more: false,
            next_offset: null, next_cursor: null, degraded: false, degraded_reason: null, stock_unavailable: false,
          };
        }
      },

      fetchStockUpdates: async () => {
        // Every loaded stock item, not just the first 100: pages loaded by scrolling used to
        // keep their first stock figure until the next full reload.
        const codes = stockRefreshCodes(get().products);
        if (codes.length === 0) return {};
        return fetchStockFor(codes);
      },

      initializePOS: async (posName: string, customerId = '') => {
        const { lastFullRefresh, products, isLoading, isInitialized, searchQuery, selectedCategory } = get();
        
        const effectiveCustomer = get().getEffectiveCustomer();
        const effectiveCustomerId = customerId || effectiveCustomer?.id || '';
        const effectivePriceList = get().getEffectivePriceList();
        
        const isCacheValid = lastFullRefresh && 
          (Date.now() - lastFullRefresh) < CACHE_DURATION && 
          products.length > 0;
        
        if (isCacheValid && !effectiveCustomerId && isInitialized && !isLoading) {
          return;
        }
        
        if (isLoading) {
          return;
        }
        
        set({ isLoading: true, error: null });
        currentPosName = posName;

        // The bar's groups in parallel with the items: a few KB that paint long before
        // the first page of items arrives.
        void get().fetchItemGroups();

        try {
          const result = await dedupeFirstPage(
            firstPageKey({
              posName,
              customerId: effectiveCustomerId,
              priceList: effectivePriceList,
              warehouse: usePOSProfileStore.getState().warehouse,
              category: 'all',
              search: '',
            }),
            () => get().fetchProductsFromAPI(PAGE_SIZE, 0, '', 'all', effectiveCustomerId, effectivePriceList, { includeCount: true })
          );

          set({
            products: result.items,
            totalCount: result.total_count ?? 0,
            hasMore: result.has_more,
            degraded: result.degraded,
            degradedReason: result.degraded_reason,
            stockUnavailable: result.stock_unavailable,
            currentOffset: resolveNextOffset(result.next_offset, result.items.length),
            currentCursor: result.next_cursor,
            isLoading: false,
            lastFullRefresh: Date.now(),
            lastUpdated: new Date(),
            error: null,
            searchQuery,
            selectedCategory,
            isInitialized: true,
          });
          
          get().startBackgroundRefresh();
          
        } catch (err) {
          set({ 
            error: err instanceof Error ? err.message : 'Failed to initialize POS',
            isLoading: false 
          });
        }
      },

      fetchProducts: async (reset = true) => {
        const { searchQuery, selectedCategory, fetchProductsFromAPI, posName } = get();
        
        if (!posName && !currentPosName) {
          return;
        }
        
        const effectiveCustomer = get().getEffectiveCustomer();
        const customerId = effectiveCustomer?.id || '';
        const priceList = get().getEffectivePriceList();
        const requestSearchQuery = searchQuery;
        const requestCategory = selectedCategory;
        const requestCustomerId = customerId;
        const requestPriceList = priceList;
        
        set({ isLoading: reset, error: null });
        
        try {
          const load = () =>
            fetchProductsFromAPI(
              reset ? PAGE_SIZE : LOAD_MORE_SIZE,
              reset ? 0 : get().currentOffset,
              requestSearchQuery,
              requestCategory,
              customerId,
              priceList,
              reset ? { includeCount: true } : { includeCount: false, cursor: get().currentCursor },
            );
          const result = reset
            ? await dedupeFirstPage(
                firstPageKey({
                  posName: posName || currentPosName,
                  customerId,
                  priceList,
                  warehouse: usePOSProfileStore.getState().warehouse,
                  category: requestCategory,
                  search: requestSearchQuery,
                }),
                load
              )
            : await load();

          // Ignore stale responses that no longer match the active query/filter/customer context.
          const latest = get();
          const latestCustomer = latest.getEffectiveCustomer();
          const latestCustomerId = latestCustomer?.id || '';
          const latestPriceList = latest.getEffectivePriceList();
          if (
            latest.searchQuery !== requestSearchQuery ||
            latest.selectedCategory !== requestCategory ||
            latestCustomerId !== requestCustomerId ||
            latestPriceList !== requestPriceList
          ) {
            set({ isLoading: false });
            return;
          }
          
          set({
            products: reset ? result.items : [...get().products, ...result.items],
            // A search narrows the bar's counts; otherwise the till's own groups stand
            // (and come back when a search is cleared).
            itemGroups:
              reset && requestSearchQuery.trim()
                ? result.item_groups
                : get().baseItemGroups.length
                  ? get().baseItemGroups
                  : get().itemGroups,
            totalCount: result.total_count ?? get().totalCount,
            hasMore: result.has_more,
            degraded: result.degraded,
            degradedReason: result.degraded_reason,
            stockUnavailable: result.stock_unavailable,
            currentOffset: resolveNextOffset(
              result.next_offset,
              reset ? result.items.length : get().currentOffset + result.items.length,
            ),
            currentCursor: result.next_cursor,
            isLoading: false,
            lastFullRefresh: Date.now(),
            lastUpdated: new Date(),
            isInitialized: true,
          });
        } catch (err) {
          set({ error: 'Failed to fetch products', isLoading: false });
        }
      },

      loadMoreProducts: async () => {
        const { isLoadingMore, hasMore, searchQuery, fetchProducts } = get();
        if (isLoadingMore || !hasMore || searchQuery) return;

        const before = { cursor: get().currentCursor, offset: get().currentOffset };

        set({ isLoadingMore: true });
        await fetchProducts(false);

        // Backstop: the grid's infinite-scroll sentinel re-fires for as long as hasMore is
        // true, so a page that leaves the position where it was loops forever. Require real
        // forward progress rather than trusting the server's has_more. A context change
        // mid-flight also lands here (the stale-response guard returns without moving the
        // position) and stopping is the right outcome there too.
        const state = get();
        const keepGoing =
          state.hasMore && pageAdvanced(before, { cursor: state.currentCursor, offset: state.currentOffset });
        set({ isLoadingMore: false, ...(keepGoing ? {} : { hasMore: false }) });
      },

      searchProducts: async (query: string, immediate = false) => {
        const trimmedQuery = query.trim();

        if (searchTimer) {
          clearTimeout(searchTimer);
          searchTimer = null;
        }
        if (identifierTimer) {
          clearTimeout(identifierTimer);
          identifierTimer = null;
        }

        set({ searchQuery: query, isSearching: true });

        if (!trimmedQuery) {
          set({ isSearching: false });
          get().fetchProducts(true);
          return;
        }

        const isIdentifierLike = IDENTIFIER_LIKE_PATTERN.test(trimmedQuery);

        // Definitive scan (hardware scan button or scanner Enter suffix): resolve
        // the exact identifier immediately and skip the heavy fuzzy search. Only
        // fall back to fuzzy when the code matched nothing and the identifier
        // lookup didn't already own the UI (e.g. scanner-only mode).
        if (immediate && isIdentifierLike) {
          const handled = await get().attemptIdentifierLookup(trimmedQuery);
          if (!handled) {
            await get().executeSearch(trimmedQuery);
          }
          return;
        }

        if (isIdentifierLike) {
          identifierTimer = setTimeout(async () => {
            // Null the handle as it fires so resolveSearchNow can tell a still
            // pending lookup from one that already ran (avoids double-processing).
            identifierTimer = null;
            await get().attemptIdentifierLookup(trimmedQuery);
          }, 50);
        }

        if (!immediate) {
          searchTimer = setTimeout(async () => {
            searchTimer = null;
            await get().executeSearch(trimmedQuery);
          }, 400);
          return;
        }

        await get().executeSearch(trimmedQuery);
      },

      // Flush any pending debounced lookup immediately (e.g. on the Enter suffix a
      // barcode scanner sends). Acts only on a *pending* timer, so if the scan has
      // already resolved this is a no-op - it can never process the same scan
      // twice. Falls back to fuzzy search only when an identifier lookup was
      // pending and matched nothing.
      resolveSearchNow: async () => {
        const query = get().searchQuery.trim();
        if (!query) return;

        const identifierPending = !!identifierTimer;
        const searchPending = !!searchTimer;

        if (identifierTimer) {
          clearTimeout(identifierTimer);
          identifierTimer = null;
        }
        if (searchTimer) {
          clearTimeout(searchTimer);
          searchTimer = null;
        }

        if (identifierPending) {
          const handled = await get().attemptIdentifierLookup(query);
          if (!handled) {
            await get().executeSearch(query);
          }
          return;
        }

        if (searchPending) {
          await get().executeSearch(query);
        }
        // Nothing was pending: the scan/search already resolved - do nothing.
      },

      executeSearch: async (query: string) => {
        const { fetchProductsFromAPI, selectedCategory } = get();
        
        const effectiveCustomer = get().getEffectiveCustomer();
        const customerId = effectiveCustomer?.id || '';
        const priceList = get().getEffectivePriceList();
        
        try {
          const result = await fetchProductsFromAPI(SEARCH_PAGE_SIZE, 0, query, selectedCategory, customerId, priceList);
          
          if (get().searchQuery.trim() === query) {
            set({
              products: result.items,
              itemGroups: result.item_groups,
              totalCount: result.total_count ?? 0,
              hasMore: false,
              degraded: result.degraded,
              degradedReason: result.degraded_reason,
              stockUnavailable: result.stock_unavailable,
              currentOffset: resolveNextOffset(result.next_offset, result.items.length),
              currentCursor: null,
              isSearching: false,
            });
          }
        } catch (err) {
          set({ error: 'Search failed', isSearching: false });
        }
      },

      // Returns true when this lookup owned the outcome (matched, or scanner-only
      // mode which drives its own UX, or a newer query already superseded it) and
      // false only when nothing matched in interactive mode, so an immediate
      // caller can decide whether to fall back to the fuzzy search.
      attemptIdentifierLookup: async (query: string): Promise<boolean> => {
        const item = await get().fetchItemByIdentifier(query);

        const profile = usePOSProfileStore.getState();
        const useScannerOnly = !!profile.useScannerOnly;
        const autoAdd = !!profile.posDetails?.auto_add_item_to_cart;

        if (useScannerOnly && autoAdd) {
          // Cancel the slower fuzzy search regardless of match outcome.
          if (searchTimer) {
            clearTimeout(searchTimer);
            searchTimer = null;
          }

          // Enqueue the add regardless of staleness - a confirmed item scanned
          // in rapid succession must never be silently dropped.
          if (item) {
            void useCartStore.getState().addToCartQueued({ ...item, item_code: item.id });
          }

          // Only clear the box if it still holds exactly this scan (no newer
          // scan is mid-type). Applies whether matched or not, so a doubled
          // barcode (two scans concatenated into one unmatched string) still
          // clears instead of sitting there as garbage.
          if (get().searchQuery.trim() === query) {
            if (!item) {
              toast.info(`No item found for ${query}`);
            }
            get().clearSearch();
          }
          // Scanner-only mode fully owns the scan UX (add or toast+clear), so the
          // caller must never fall back to a fuzzy search.
          return true;
        }

        // ---- non-scanner-only behavior ----
        // The user kept typing/scanning since this lookup was scheduled - a newer
        // query is already driving the UI, so treat this as handled.
        if (get().searchQuery.trim() !== query) return true;
        // No identifier match: let the caller fall back to fuzzy search.
        if (!item) return false;

        // Exact identifier match: cancel the slower fuzzy search and show
        // just this item immediately.
        if (searchTimer) {
          clearTimeout(searchTimer);
          searchTimer = null;
        }

        set({
          products: [item],
          totalCount: 1,
          hasMore: false,
          isSearching: false,
        });

        if (autoAdd) {
          await useCartStore.getState().addToCart({ ...item, item_code: item.id });
          get().clearSearch();
        }
        return true;
      },

      fetchItemByIdentifier: async (code: string) => {
        try {
          const response = await fetch(
            `/api/method/klik_pos.api.item.item_search.get_item_by_identifier?code=${encodeURIComponent(code)}`
          );
          if (!response.ok) return null;

          const data = await response.json();
          const message = data?.message;
          if (!message?.item_code) return null;

          const item: MenuItem = {
            id: message.item_code,
            item_code: message.item_code,
            name: message.item_name || message.item_code,
            category: message.item_group || 'General',
            price: message.price || 0,
            image: message.image || '',
            available: message.available || 0,
            is_stock_item: message.is_stock_item,
            sold: 0,
            description: message.description || '',
            currency_symbol: message.currency_symbol,
            is_product_bundle: message.is_product_bundle || false,
            bundle_items: message.bundle_items || [],
            is_variant_template: message.is_variant_template || false,
            has_variants: message.has_variants || false,
            variant_of: message.variant_of,
            variant_based_on: message.variant_based_on,
          };
          return item;
        } catch {
          return null;
        }
      },

      clearSearch: () => {
        if (searchTimer) {
          clearTimeout(searchTimer);
          searchTimer = null;
        }
        if (identifierTimer) {
          clearTimeout(identifierTimer);
          identifierTimer = null;
        }
        set({ searchQuery: '' });
        get().fetchProducts(true);
      },

      setCategory: (category: string) => {
        const { selectedCategory, searchQuery } = get();
        if (selectedCategory === category) return;
        
        set({ selectedCategory: category });
        
        if (!searchQuery) {
          get().fetchProducts(true);
        }
      },

      refreshStockOnly: () => {
        if (!stockRefreshRun) {
          stockRefreshRun = get().refreshStockNow().finally(() => { stockRefreshRun = null; });
          return stockRefreshRun;
        }
        if (!stockRefreshQueued) {
          stockRefreshQueued = stockRefreshRun.then(() => {
            stockRefreshQueued = null;
            return get().refreshStockOnly();
          });
        }
        return stockRefreshQueued;
      },

      refreshStockNow: async () => {
        set({ isRefreshingStock: true });

        try {
          const stockUpdates = await get().fetchStockUpdates();
          const products = applyStockUpdates(get().products, stockUpdates);
          if (products !== get().products) {
            set({ products, lastUpdated: new Date(), isRefreshingStock: false });
            return true;
          }
          set({ isRefreshingStock: false });
          return false;
        } catch (error) {
          console.error('Stock refresh failed:', error);
          set({ isRefreshingStock: false });
          return false;
        }
      },

      updateStockOnly: (itemCode: string, newStock: number) => {
        set(state => ({
          products: state.products.map(product =>
            product.id === itemCode ? { ...product, available: newStock } : product
          )
        }));
      },

      updateStockForItems: async (itemCodes: string[]) => {
        if (itemCodes.length === 0) return;
        const stockUpdates = await fetchStockFor(itemCodes);
        set((state) => {
          const products = applyStockUpdates(state.products, stockUpdates);
          return products === state.products ? state : { products };
        });
      },

      searchCustomers: async (query: string) => {
        if (!query.trim()) {
          set({ customers: [], isLoadingCustomers: false });
          return [];
        }
        
        set({ isLoadingCustomers: true });
        
        try {
          const response = await fetch(
            `/api/method/klik_pos.api.customer.customer_search.search_customers?query=${encodeURIComponent(query)}&pos_profile=${encodeURIComponent(currentPosName)}`
          );
          
          if (!response.ok) throw new Error('Failed to fetch customers');
          
          const data = await response.json();
          const customers = data?.message?.customers || [];
          
          set({ customers, isLoadingCustomers: false });
          return customers;
        } catch (error) {
          console.error('Customer search failed:', error);
          set({ isLoadingCustomers: false });
          return [];
        }
      },

      setSelectedCustomer: (customer: Customer | null) => {
        set({ selectedCustomer: customer });
        
        useCartStore.getState().setSelectedCustomer(customer);
        
        if (currentPosName && customer) {
          get().initializePOS(currentPosName, customer?.id || '');
        }
      },

      clearCache: () => {
        get().stopBackgroundRefresh();
        
        set({
          products: [],
          itemGroups: [],
          baseItemGroups: [],
          customers: [],
          selectedCustomer: null,
          searchQuery: '',
          selectedCategory: 'all',
          totalCount: 0,
          hasMore: false,
          currentOffset: 0,
          currentCursor: null,
          isLoading: false,
          isLoadingMore: false,
          isSearching: false,
          isLoadingCustomers: false,
          isRefreshingStock: false,
          error: null,
          lastFullRefresh: null,
          lastUpdated: null,
          isInitialized: false,
          posName: null,
        });
        
        localStorage.removeItem('product-storage');
      },

      fetchItemGroups: async () => {
        try {
          const params = new URLSearchParams();
          const warehouse = usePOSProfileStore.getState().warehouse;
          if (warehouse) params.append('warehouse', warehouse);
          const response = await fetch(
            `/api/method/klik_pos.api.item.item_listing.get_item_groups?${params.toString()}`
          );
          if (!response.ok) return;
          const data = await response.json();
          const groups: ItemGroup[] = Array.isArray(data?.message) ? data.message : [];
          set((state) => ({
            baseItemGroups: groups,
            // A running search keeps its narrowed counts until it is cleared.
            itemGroups: state.searchQuery.trim() ? state.itemGroups : groups,
          }));
        } catch (err) {
          // The bar keeps what it has; the next load tries again.
          console.error('fetchItemGroups error:', err);
        }
      },

      startBackgroundRefresh: () => {
        get().stopBackgroundRefresh();
        
        const stockInterval = setInterval(() => {
          const { isSearching, isLoading } = get();
          if (document.visibilityState === 'visible' && !isSearching && !isLoading) {
            get().refreshStockOnly();
          }
        }, 30000);
        
        // No timed reload of the list: it threw the cashier back to page 1 and re-downloaded
        // the first page every 5 minutes. Stock refreshes in place (above); the list itself
        // reloads on real triggers - category, search, customer, price list, profile change.
        // The category bar's counts are cheap to keep fresh.
        const fullRefreshInterval = setInterval(() => {
          if (document.visibilityState === 'visible') {
            void get().fetchItemGroups();
          }
        }, CACHE_DURATION);
        
        refreshTimers = [stockInterval, fullRefreshInterval];
        
        const handleFocus = () => {
          const { lastFullRefresh, searchQuery } = get();
          if (lastFullRefresh && (Date.now() - lastFullRefresh) > 120000 && !searchQuery) {
            get().refreshStockOnly();
          }
        };
        
        window.addEventListener('focus', handleFocus);
        (window as any).__posFocusHandler = handleFocus;
      },

      stopBackgroundRefresh: () => {
        refreshTimers.forEach(timer => clearInterval(timer));
        refreshTimers = [];
        
        const handler = (window as any).__posFocusHandler;
        if (handler) {
          window.removeEventListener('focus', handler);
          delete (window as any).__posFocusHandler;
        }
      },
    }),
    {
      name: 'product-storage',
      // v1 stops keeping isInitialized; a v0 blob on a till still holds `true`, which would
      // stop the list from ever loading after the upgrade - drop it.
      version: 1,
      migrate: (persisted) => {
        const rest = { ...((persisted ?? {}) as Record<string, unknown>) };
        delete rest.isInitialized;
        return rest as unknown as ProductStoreState;
      },
      // Products are not kept between visits, so neither is isInitialized: a reload must
      // load the list again through the one normal path. The bar's groups are kept (the
      // till's own, never a search's) so it paints at once and refreshes quietly.
      partialize: (state) => ({
        itemGroups: state.baseItemGroups.length ? state.baseItemGroups : state.itemGroups,
        baseItemGroups: state.baseItemGroups,
        lastFullRefresh: state.lastFullRefresh,
        selectedCustomer: state.selectedCustomer,
        posName: state.posName,
      }),
    }
  )
);

if (typeof window !== 'undefined') {
  setTimeout(() => {
    const profileState = usePOSProfileStore.getState();
    if (profileState.isInitialized && profileState.posDetails?.name) {
      useProductStore.getState().checkAndInitialize();
    }
  }, 100);
  
  let previousProfileState = usePOSProfileStore.getState();
  
  const unsubscribeProfile = usePOSProfileStore.subscribe((state) => {
    const productStore = useProductStore.getState();
    
    if (state.isInitialized && state.posDetails?.name && !productStore.isInitialized && !productStore.isLoading) {
      productStore.checkAndInitialize();
    }
    
    // The profile ARRIVING is not a change of settings: only compare once it had loaded,
    // or every till start would reload the list a second time.
    if (previousProfileState.isInitialized &&
        (previousProfileState.hideUnavailableItems !== state.hideUnavailableItems ||
         previousProfileState.useScannerOnly !== state.useScannerOnly)) {
      if (productStore.isInitialized && !productStore.searchQuery.trim()) {
        productStore.fetchProducts(true);
        // Hiding unavailable items changes the counts too.
        void productStore.fetchItemGroups();
      }
    }
    
    previousProfileState = state;
  });

  let previousSelectedPriceList = useCartStore.getState().selectedPriceList;
  const unsubscribePriceList = useCartStore.subscribe((state) => {
    if (state.selectedPriceList === previousSelectedPriceList) {
      return;
    }

    previousSelectedPriceList = state.selectedPriceList;
    const productStore = useProductStore.getState();
    if (productStore.isInitialized) {
      productStore.fetchProducts(true);
    }
  });
  
  if ((window as any).__productStoreUnsubscribe) {
    (window as any).__productStoreUnsubscribe();
  }
  (window as any).__productStoreUnsubscribe = () => {
    unsubscribeProfile();
    unsubscribePriceList();
  };
}
