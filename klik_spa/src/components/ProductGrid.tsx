"use client";

import { useEffect, useRef, useCallback, useMemo, useState } from "react";
import type { MenuItem } from "../../types";
import { useProduct } from "../providers/ProductProvider";
import ProductCard from "./ProductCard";
import ProductLineView from "./ProductLineView";
import SalespersonAuthModal from "./dialog/SalespersonAuthModal";
import VariantPickerModal from "./VariantPickerModal";
import { useCartStore } from "../stores/cartStore";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useSalespersonStore } from "../stores/salespersonStore";
import { isItemOutOfStock } from "../utils/stock";
import { appendDigit, deleteDigit, bufferToQuantity, OVERFLOW } from "../utils/quantityBuffer";


interface ProductGridProps {
  isMobile?: boolean;
  scannerOnly?: boolean;
  viewMode?: "grid" | "list";
  hasMore?: boolean;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
  totalCount?: number;
  isSearching?: boolean;
}

export default function ProductGrid({
  isMobile = false,
  scannerOnly = false,
  viewMode: propViewMode,
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
  totalCount = 0,
  isSearching = false,
}: ProductGridProps) {
  const { filteredItems, hideUnavailableItems, selectedCustomer, degraded, degradedReason, stockUnavailable } = useProduct();
  const { addToCartWithQuantity, cartItems, updateQuantity, removeItem } = useCartStore();
  const { posDetails } = usePOSProfileStore();
  const { activeSalesperson, ensureInitialized, isRestoring } = useSalespersonStore();
  const [showSalespersonModal, setShowSalespersonModal] = useState(false);
  // Carries the quantity the cashier had typed before the PIN prompt interrupted them,
  // so resuming after a correct PIN adds what was actually typed instead of silently
  // dropping it back to 1.
  const [pendingCartItem, setPendingCartItem] = useState<{ item: MenuItem; quantity: number } | null>(null);
  const [variantTemplateItem, setVariantTemplateItem] = useState<MenuItem | null>(null);

  const defaultView = posDetails?.custom_default_view || "Grid View";
  const viewMode = propViewMode || (defaultView === "List View" ? "list" : "grid");
  const showItemCode = !!posDetails?.custom_show_item_code_in_product_list;
  const hideImages = !!posDetails?.hide_images;
  const requiresSalespersonPin = !!posDetails?.custom_sales_person_pin_required;
  const isSalespersonLockActive = requiresSalespersonPin && !activeSalesperson && !isRestoring;

  const [focusedIndex, setFocusedIndex] = useState(-1);

  const [quantityBuffer, setQuantityBuffer] = useState("");
  // OVERFLOW is a real, meaningful buffer state (it means "1", stickily, until a
  // terminator clears it) but it is not a quantity a cashier typed — the badge must
  // show nothing for it rather than the sentinel character itself.
  const displayQuantityBuffer = quantityBuffer === OVERFLOW ? "" : quantityBuffer;

  // A scanner-only till types barcodes into whatever is focused; digits there are
  // never a quantity, so the shortcut is switched off entirely.
  const quantityShortcutEnabled = !scannerOnly;

  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Mirrors the backend's stand-down: when stock could not be read every balance is 0, so
  // this client-side filter would blank the grid and undo the whole point of the server
  // returning the full catalogue. Passing the flag keeps the two in step.
  const inStockItems = useMemo(
    () => (
      hideUnavailableItems && !stockUnavailable
        ? filteredItems.filter((item) => !isItemOutOfStock(item, stockUnavailable))
        : filteredItems
    ),
    [filteredItems, hideUnavailableItems, stockUnavailable],
  );

  // inStockItems is a fresh array identity every render — productStore's
  // getFilteredItems() returns a new filter(...) result on every call, and the
  // background 30s stock refresh triggers one even when the item set itself hasn't
  // changed. Keying on identity would wipe focus and the in-progress quantity buffer
  // on a mere stock tick; keying on the item set means a genuine search/filter/
  // pagination change still resets both, while a stock-value-only refresh leaves them
  // alone.
  const itemsSignature = useMemo(() => inStockItems.map((item) => item.id).join('|'), [inStockItems]);
  useEffect(() => { setFocusedIndex(-1); setQuantityBuffer(""); }, [itemsSignature]);

  // Structural guarantee that the buffer never survives a focus change, however it
  // happens: arrow keys, Tab/Shift+Tab, a click on another row, or MenuGrid's F3 ->
  // ArrowDown jump straight to index 0. Typing a digit never changes focusedIndex, so
  // this never fires mid-buffer.
  useEffect(() => { setQuantityBuffer(''); }, [focusedIndex]);

  useEffect(() => {
    if (requiresSalespersonPin) {
      void ensureInitialized();
    }
  }, [requiresSalespersonPin, ensureInitialized]);

  useEffect(() => {
    if (isSalespersonLockActive) {
      setShowSalespersonModal(true);
      return;
    }

    setShowSalespersonModal(false);
    setPendingCartItem(null);
  }, [isSalespersonLockActive]);

  const addConcreteItemToCart = useCallback(async (item: MenuItem, quantity = 1) => {
    await addToCartWithQuantity({ ...item, item_code: item.id }, quantity);
  }, [addToCartWithQuantity]);

  const addItemToCart = useCallback(async (item: MenuItem, quantity = 1) => {
    if (item.is_variant_template || item.has_variants) {
      setVariantTemplateItem(item);
      return;
    }

    await addConcreteItemToCart(item, quantity);
  }, [addConcreteItemToCart]);

  const handleAddToCart = useCallback(async (item: MenuItem, quantity = 1) => {
    if (isItemOutOfStock(item, stockUnavailable)) return;
    if (scannerOnly) return;

    if (requiresSalespersonPin) {
      await ensureInitialized();

      const {
        activeSalesperson: currentSalesperson,
        isRestoring: isCurrentlyRestoring,
      } = useSalespersonStore.getState();

      if (isCurrentlyRestoring) {
        return;
      }

      if (!currentSalesperson) {
        setPendingCartItem({ item, quantity });
        setShowSalespersonModal(true);
        return;
      }
    }

    await addItemToCart(item, quantity);
  }, [addItemToCart, ensureInitialized, requiresSalespersonPin, scannerOnly, stockUnavailable]);

  const handleItemKeyDown = useCallback((index: number, item: MenuItem, e: React.KeyboardEvent) => {
    if (quantityShortcutEnabled) {
      // Ctrl/Cmd/Alt+digit are browser and OS bindings (switch tab, reset zoom, ...),
      // never a typed quantity — let them fall through untouched rather than
      // swallowing them and appending a phantom digit.
      if (/^[0-9]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setQuantityBuffer((current) => appendDigit(current, e.key));
        return;
      }
      if (e.key === 'Backspace' && quantityBuffer !== '') {
        // Only while the buffer holds something. Empty, it must still fall through
        // to the global "jump back to the search box" binding.
        e.preventDefault();
        setQuantityBuffer((current) => deleteDigit(current));
        return;
      }
      if (e.key === 'Escape' && quantityBuffer !== '') {
        e.preventDefault();
        setQuantityBuffer('');
        return;
      }
    }

    if (e.key === 'ArrowDown') {
      // Redundant with the focusedIndex effect above once the next row actually takes
      // focus (its onFocus will clear the buffer too) — kept anyway as a same-tick clear
      // so the badge never flashes stale for a frame, and it's free.
      e.preventDefault();
      setQuantityBuffer('');
      document.querySelector<HTMLElement>(`[data-product-index="${index + 1}"]`)?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setQuantityBuffer('');
      if (index === 0) {
        // This jump goes to the search input, not another product row, so
        // focusedIndex never changes and the focusedIndex effect above will NOT
        // fire — this explicit clear is the only thing that clears the buffer here.
        const el = document.getElementById('pos-search-input') as HTMLInputElement | null;
        el?.focus();
        el?.select();
      } else {
        document.querySelector<HTMLElement>(`[data-product-index="${index - 1}"]`)?.focus();
      }
    } else if (e.key === '+' || e.key === '=' || e.key === 'Enter') {
      e.preventDefault();
      const quantity = bufferToQuantity(quantityBuffer);
      setQuantityBuffer('');
      void handleAddToCart(item, quantity);
    } else if (e.key === '-') {
      e.preventDefault();
      const step = bufferToQuantity(quantityBuffer);
      setQuantityBuffer('');
      const cartItem = cartItems.find(ci => (ci.item_code || ci.id) === (item.item_code || item.id));
      if (cartItem) {
        if (cartItem.quantity <= step) {
          removeItem(cartItem.id);
        } else {
          void updateQuantity(cartItem.id, cartItem.quantity - step);
        }
      }
    }
  }, [cartItems, handleAddToCart, quantityBuffer, quantityShortcutEnabled, removeItem, updateQuantity]);

  const handleSalespersonAuthenticated = useCallback(() => {
    const itemToAdd = pendingCartItem;
    setPendingCartItem(null);
    setShowSalespersonModal(false);

    if (!itemToAdd) {
      return;
    }

    void addItemToCart(itemToAdd.item, itemToAdd.quantity);
  }, [addItemToCart, pendingCartItem]);

  const handleVariantSelected = useCallback(async (variant: MenuItem) => {
    await addConcreteItemToCart(variant);
  }, [addConcreteItemToCart]);

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const target = entries[0];
      if (!target) return;
      if (target.isIntersecting && hasMore && !isLoadingMore && onLoadMore) {
        onLoadMore();
      }
    },
    [hasMore, isLoadingMore, onLoadMore],
  );

  useEffect(() => {
    const option = {
      root: null,
      rootMargin: "200px",
      threshold: 0,
    };

    const observer = new IntersectionObserver(handleObserver, option);
    const currentLoadMoreRef = loadMoreRef.current;

    if (currentLoadMoreRef) {
      observer.observe(currentLoadMoreRef);
    }

    return () => {
      if (currentLoadMoreRef) {
        observer.unobserve(currentLoadMoreRef);
      }
    };
  }, [handleObserver]);

  // Same amber treatment as CustomerReceivablesTable, so a degraded response reads as one
  // system wherever it appears. Rendered in every branch below - including the empty state,
  // which is exactly where a cashier most needs to know a permission is missing rather than
  // assuming the shop has no stock.
  const degradationBanner = degraded ? (
    <div
      role="status"
      className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
    >
      {degradedReason || "Some data could not be read for your role, so figures may be incomplete."}
    </div>
  ) : null;

  if (viewMode === "list") {
    return (
      <>
        {degradationBanner}
        <div className="flex flex-col relative">
        {isSearching && (
          <div className="absolute inset-0 bg-white/50 dark:bg-gray-900/50 z-10 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-beveren-600"></div>
          </div>
        )}
        <ProductLineView
          stockUnavailable={stockUnavailable}
          items={inStockItems}
          onAddToCart={handleAddToCart}
          isMobile={isMobile}
          showItemCode={showItemCode}
          scannerOnly={scannerOnly}
          hideImages={hideImages}
          focusedIndex={focusedIndex}
          onItemFocus={setFocusedIndex}
          onItemKeyDown={handleItemKeyDown}
          quantityBuffer={displayQuantityBuffer}
        />

        {onLoadMore && (
          <div ref={loadMoreRef} className="py-4 flex justify-center">
            {isLoadingMore && (
              <div className="flex items-center space-x-2">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-beveren-600"></div>
                <span className="text-gray-500 dark:text-gray-400 text-sm">
                  Loading more items...
                </span>
              </div>
            )}
            {!isLoadingMore && hasMore && (
              <span className="text-gray-400 dark:text-gray-500 text-sm">
                Showing {inStockItems.length} of {totalCount} items
              </span>
            )}
            {!hasMore && inStockItems.length > 0 && (
              <span className="text-gray-400 dark:text-gray-500 text-sm">
                All {inStockItems.length} items loaded
              </span>
            )}
          </div>
        )}
        </div>

        <SalespersonAuthModal
          isOpen={showSalespersonModal}
          onClose={() => {
            setShowSalespersonModal(false);
            setPendingCartItem(null);
          }}
          onAuthenticated={handleSalespersonAuthenticated}
          title="Verify salesperson"
          description="Verify the salesperson before adding items to the cart."
        />
        {variantTemplateItem && (
          <VariantPickerModal
            item={variantTemplateItem}
            customerId={selectedCustomer?.id}
            onClose={() => setVariantTemplateItem(null)}
            onSelectVariant={handleVariantSelected}
          />
        )}
      </>
    );
  }

  if (inStockItems.length === 0 && !isSearching) {
    return (
      <>
        {degradationBanner}
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              No items found
            </h3>
            <p className="text-gray-500 dark:text-gray-400">
              Try adjusting your search or filters
            </p>
          </div>
        </div>

        <SalespersonAuthModal
          isOpen={showSalespersonModal}
          onClose={() => {
            if (isSalespersonLockActive) {
              return;
            }
            setShowSalespersonModal(false);
            setPendingCartItem(null);
          }}
          onAuthenticated={handleSalespersonAuthenticated}
          allowDismiss={!isSalespersonLockActive}
          title={isSalespersonLockActive ? "Unlock POS" : "Verify salesperson"}
          description={
            isSalespersonLockActive
              ? "Enter the salesperson PIN to unlock this POS session and continue."
              : "Verify the salesperson before adding items to the cart."
          }
        />
        {variantTemplateItem && (
          <VariantPickerModal
            item={variantTemplateItem}
            customerId={selectedCustomer?.id}
            onClose={() => setVariantTemplateItem(null)}
            onSelectVariant={handleVariantSelected}
          />
        )}
      </>
    );
  }

  return (
    <>
      {degradationBanner}
      <div className={`${isMobile ? "p-3" : "p-6"} bg-gray-50 dark:bg-gray-900 relative`}>
      {isSearching && (
        <div className="absolute inset-0 bg-white/50 dark:bg-gray-900/50 z-10 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-beveren-600"></div>
        </div>
      )}
      <div className={`grid ${isMobile ? "gap-3 grid-cols-2 sm:grid-cols-2" : "gap-4 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-4"}`}>
        {inStockItems.map((item, i) => (
          <ProductCard
            stockUnavailable={stockUnavailable}
            key={item.id}
            item={item}
            onAddToCart={handleAddToCart}
            isMobile={isMobile}
            showItemCode={showItemCode}
            scannerOnly={scannerOnly}
            productIndex={i}
            isFocused={focusedIndex === i}
            onFocused={() => setFocusedIndex(i)}
            onKeyboardAction={(e) => handleItemKeyDown(i, item, e)}
            quantityBuffer={focusedIndex === i ? displayQuantityBuffer : ""}
          />
        ))}
      </div>

      {onLoadMore && (
        <div ref={loadMoreRef} className="py-6 flex justify-center">
          {isLoadingMore && (
            <div className="flex items-center space-x-2">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-beveren-600"></div>
              <span className="text-gray-500 dark:text-gray-400 text-sm">
                Loading more items...
              </span>
            </div>
          )}
          {!isLoadingMore && hasMore && (
            <span className="text-gray-400 dark:text-gray-500 text-sm">
              Showing {inStockItems.length} of {totalCount} items • Scroll for more
            </span>
          )}
          {!hasMore && inStockItems.length > 0 && totalCount > 0 && (
            <span className="text-gray-400 dark:text-gray-500 text-sm">
              All {inStockItems.length} items loaded
            </span>
          )}
        </div>
      )}
      </div>

      <SalespersonAuthModal
        isOpen={showSalespersonModal}
        onClose={() => {
          if (isSalespersonLockActive) {
            return;
          }
          setShowSalespersonModal(false);
          setPendingCartItem(null);
        }}
        onAuthenticated={handleSalespersonAuthenticated}
        allowDismiss={!isSalespersonLockActive}
        title={isSalespersonLockActive ? "Unlock POS" : "Verify salesperson"}
        description={
          isSalespersonLockActive
            ? "Enter the salesperson PIN to unlock this POS session and continue."
            : "Verify the salesperson before adding items to the cart."
        }
      />
      {variantTemplateItem && (
        <VariantPickerModal
          item={variantTemplateItem}
          customerId={selectedCustomer?.id}
          onClose={() => setVariantTemplateItem(null)}
          onSelectVariant={handleVariantSelected}
        />
      )}
    </>
  );
}
