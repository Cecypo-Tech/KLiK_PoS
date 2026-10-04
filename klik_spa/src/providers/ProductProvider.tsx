import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useProductStore } from '../stores/productStore';
import { usePOSProfileStore } from '../stores/posProfileStore';
import { filterAvailableProducts } from '../utils/productFilter';
import type { MenuItem, POSProfile, Customer, ItemGroup } from '../../types';

interface ProductContextType {
  products: MenuItem[];
  filteredItems: MenuItem[];
  posDetails: POSProfile | null;
  itemGroups: ItemGroup[];
  customers: Customer[];
  selectedCustomer: Customer | null;
  
  searchQuery: string;
  selectedCategory: string;
  
  totalCount: number;
  hasMore: boolean;
  degraded: boolean;
  degradedReason: string | null;
  stockUnavailable: boolean;
  
  isLoading: boolean;
  isLoadingMore: boolean;
  isSearching: boolean;
  isLoadingCustomers: boolean;
  error: string | null;
  
  useScannerOnly: boolean;
  hideUnavailableItems: boolean;
  scalePrefix: string;
  defaultView: 'grid' | 'list';
  
  initializePOS: (posName: string, customerId?: string) => Promise<void>;
  fetchProducts: (reset?: boolean) => Promise<void>;
  loadMoreProducts: () => Promise<void>;
  searchProducts: (query: string, immediate?: boolean) => Promise<void>;
  resolveSearchNow: () => Promise<void>;
  clearSearch: () => void;
  setCategory: (category: string) => void;
  refreshStockOnly: () => Promise<boolean>;
  updateStockOnly: (itemCode: string, newStock: number) => void;
  updateStockForItems: (itemCodes: string[]) => Promise<void>;
  searchCustomers: (query: string) => Promise<Customer[]>;
  setSelectedCustomer: (customer: Customer | null) => void;
  clearCache: () => void;
}

const ProductContext = createContext<ProductContextType | undefined>(undefined);

interface ProductProviderProps {
  children: ReactNode;
  posName: string;
  initialCustomerId?: string;
}

export function ProductProvider({ children, posName, initialCustomerId }: ProductProviderProps) {
  // Field-by-field subscriptions and a memoized value: the whole-store subscription rebuilt
  // the context - and redrew every consumer - on any change at all. isRefreshingStock and
  // lastUpdated are left out (no consumer reads them) so stock ticks do not redraw the tree.
  const state = useProductStore(
    useShallow((s) => ({
      products: s.products,
      itemGroups: s.itemGroups,
      customers: s.customers,
      selectedCustomer: s.selectedCustomer,
      searchQuery: s.searchQuery,
      selectedCategory: s.selectedCategory,
      totalCount: s.totalCount,
      hasMore: s.hasMore,
      degraded: s.degraded,
      degradedReason: s.degradedReason,
      stockUnavailable: s.stockUnavailable,
      isLoading: s.isLoading,
      isLoadingMore: s.isLoadingMore,
      isSearching: s.isSearching,
      isLoadingCustomers: s.isLoadingCustomers,
      error: s.error,
    })),
  );
  const actions = useProductStore(
    useShallow((s) => ({
      initializePOS: s.initializePOS,
      fetchProducts: s.fetchProducts,
      loadMoreProducts: s.loadMoreProducts,
      searchProducts: s.searchProducts,
      resolveSearchNow: s.resolveSearchNow,
      clearSearch: s.clearSearch,
      setCategory: s.setCategory,
      refreshStockOnly: s.refreshStockOnly,
      updateStockOnly: s.updateStockOnly,
      updateStockForItems: s.updateStockForItems,
      searchCustomers: s.searchCustomers,
      setSelectedCustomer: s.setSelectedCustomer,
      clearCache: s.clearCache,
      stopBackgroundRefresh: s.stopBackgroundRefresh,
    })),
  );
  const profile = usePOSProfileStore(
    useShallow((p) => ({
      useScannerOnly: p.useScannerOnly,
      hideUnavailableItems: p.hideUnavailableItems,
      scalePrefix: p.scalePrefix,
      defaultView: p.defaultView,
    })),
  );

  // `actions` keeps its identity (useShallow over store functions that never change), so
  // this runs again only for a different till or customer.
  useEffect(() => {
    if (posName) {
      actions.initializePOS(posName, initialCustomerId);
    }
    return () => {
      actions.stopBackgroundRefresh();
    };
  }, [posName, initialCustomerId, actions]);

  const filteredItems = useMemo(
    () => filterAvailableProducts(state.products, profile.hideUnavailableItems),
    [state.products, profile.hideUnavailableItems],
  );

  const contextValue = useMemo<ProductContextType>(
    () => ({
      ...state,
      ...profile,
      filteredItems,
      initializePOS: actions.initializePOS,
      fetchProducts: actions.fetchProducts,
      loadMoreProducts: actions.loadMoreProducts,
      searchProducts: actions.searchProducts,
      resolveSearchNow: actions.resolveSearchNow,
      clearSearch: actions.clearSearch,
      setCategory: actions.setCategory,
      refreshStockOnly: actions.refreshStockOnly,
      updateStockOnly: actions.updateStockOnly,
      updateStockForItems: actions.updateStockForItems,
      searchCustomers: actions.searchCustomers,
      setSelectedCustomer: actions.setSelectedCustomer,
      clearCache: actions.clearCache,
    }),
    [state, profile, filteredItems, actions],
  );
  
  return (
    <ProductContext.Provider value={contextValue}>
      {children}
    </ProductContext.Provider>
  );
}

export function useProduct() {
  const context = useContext(ProductContext);
  if (context === undefined) {
    throw new Error('useProduct must be used within a ProductProvider');
  }
  return context;
}

export { useProductStore };