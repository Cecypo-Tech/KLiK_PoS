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
import { buildPriceOptions, cyclePriceOptionIndex, type PriceOption } from "../utils/priceOptions";
import PriceListPopup from "./PriceListPopup";

interface PriceListEntry {
  price_list: string;
  rate: number;
  uom?: string;
}


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
  const { addToCartWithQuantity, cartItems, updateQuantity, removeItem, toggleItemExpansion, expandedCartItemId, requestCustomRate } = useCartStore();
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
  const useItemCodeAsName = !!posDetails?.custom_use_item_code_as_display_name;
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

  const [pricePopup, setPricePopup] = useState<{
    rowIndex: number;
    item: MenuItem;
    options: PriceOption[];
    selectedIndex: number;
    customValue: string;
    position: { left: number; top?: number; bottom?: number };
  } | null>(null);
  const allowRateChange = !!posDetails?.allow_rate_change;
  // The price-list entries themselves need BOTH flags, mirroring the cart's own
  // price-list <select> (CartItemRow.tsx): rendered under allow_price_list_switching,
  // but disabled unless allow_rate_change is also on. allowRateChange alone still
  // gates the separate "Custom Price" entry, the same way it alone gates the Rate
  // field - a till with only allow_rate_change on can still type a custom price
  // without being handed every price list to switch between.
  const allowPriceListOptions = allowRateChange && !!posDetails?.allow_price_list_switching;
  const isTaxIncludedInBasicRate =
    posDetails?.is_tax_included_in_basic_rate === 1
    || posDetails?.is_tax_included_in_basic_rate === "1"
    || posDetails?.is_tax_included_in_basic_rate === true;

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
  useEffect(() => { setFocusedIndex(-1); setQuantityBuffer(""); setPricePopup(null); }, [itemsSignature]);

  // Structural guarantee that the buffer never survives a focus change, however it
  // happens: arrow keys, Tab/Shift+Tab, a click on another row, or MenuGrid's F3 ->
  // ArrowDown jump straight to index 0. Typing a digit never changes focusedIndex, so
  // this never fires mid-buffer. The price popup gets the same guarantee for the
  // same reason.
  useEffect(() => { setQuantityBuffer(''); setPricePopup(null); }, [focusedIndex]);

  // The popup only auto-closes on a focus/item-set change (above) or Escape -
  // neither fires for a click on the search box, the cart, or anywhere else
  // that never takes row focus, so without this it would sit on screen
  // (position: fixed, high z-index) eating clicks meant for whatever's under it.
  useEffect(() => {
    if (!pricePopup) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      const popupEl = document.querySelector('[data-price-popup]');
      if (popupEl?.contains(target)) return;
      const rowEl = document.querySelector(`[data-product-index="${pricePopup.rowIndex}"]`);
      if (rowEl?.contains(target)) return;
      setPricePopup(null);
    };
    document.addEventListener('mousedown', handlePointerDown, true);
    return () => document.removeEventListener('mousedown', handlePointerDown, true);
  }, [pricePopup]);

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

  const openPricePopup = useCallback(async (rowIndex: number, item: MenuItem) => {
    const warehouse = posDetails?.warehouse || "";
    try {
      const response = await fetch(
        `/api/method/klik_pos.api.item.item_details.get_full_pricing_and_batch_details?item_code=${encodeURIComponent(item.item_code || item.id)}&warehouse=${encodeURIComponent(warehouse)}`
      );
      const data = await response.json();

      // The focused row may have changed while this request was in flight
      // (arrow-key navigation doesn't wait for it) - opening anchored to a row
      // that's no longer focused would leave an orphaned popup nothing can
      // reach, since key handling is gated on the popup's own rowIndex.
      const stillFocused = document.activeElement?.getAttribute("data-product-index") === String(rowIndex);
      if (!stillFocused) return;

      const allPriceLists: PriceListEntry[] = data?.message?.price_lists || [];
      // Same filter the cart's own price-list UI applies (CartItemRow.tsx): a
      // price list quoted in a different UOM isn't a valid rate for this line,
      // and a 0 rate is "not priced here", not a real option.
      const priceLists = allPriceLists.filter(
        (p) => (!p.uom || p.uom === item.uom) && Number(p.rate || 0) > 0
      );
      const options = buildPriceOptions(allowPriceListOptions ? priceLists : [], allowRateChange, Number(item.price) || 0);
      if (options.length === 0) return;

      const rowEl = document.querySelector<HTMLElement>(`[data-product-index="${rowIndex}"]`);
      const rect = rowEl?.getBoundingClientRect();
      if (!rect) return;

      const customOption = options.find((o) => o.isCustom);
      const popupWidth = 224;
      const estimatedHeight = options.length * 40 + 16;
      const openBelow = rect.bottom + estimatedHeight <= window.innerHeight;

      setPricePopup({
        rowIndex,
        item,
        options,
        selectedIndex: 0,
        customValue: customOption ? String(customOption.rate) : "",
        position: {
          left: Math.min(rect.left, Math.max(8, window.innerWidth - popupWidth - 8)),
          ...(openBelow ? { top: rect.bottom + 6 } : { bottom: window.innerHeight - rect.top + 6 }),
        },
      });
    } catch (error) {
      console.error("Failed to load price list options:", error);
    }
  }, [posDetails, allowRateChange, allowPriceListOptions]);

  // Reuses the exact add-to-cart path '+' already uses (new line or bump an
  // existing one by `quantity`), then layers the chosen rate on top via the
  // store's rate-override request - see cartStore's requestCustomRate and
  // OrderSummary's handling of it for why this doesn't set the rate directly.
  //
  // `rate: null` means "no override" (an empty/invalid typed custom price) -
  // still adds/bumps the line, just without touching its price.
  //
  // handleAddToCart has several silent decline paths (out of stock, scanner-only,
  // a stock cap inside addToCartWithQuantity, a pending salesperson PIN) - it
  // does not throw, so success can't be read from whether the await resolved.
  // highlightNonce only advances when the store actually wrote a line
  // (cartStore.ts's addToCart/addToCartWithQuantity), so comparing it before and
  // after is what tells a decline apart from a real add, and highlightItemId
  // names the exact line that was touched - the one this rate belongs on, even
  // if a duplicate line (same item_code, different id) exists.
  const commitPriceSelection = useCallback(async (item: MenuItem, quantity: number, rate: number | null, includesTax: boolean) => {
    if (rate === null) {
      await handleAddToCart(item, quantity);
      return;
    }

    const nonceBefore = useCartStore.getState().highlightNonce;
    await handleAddToCart(item, quantity);
    const { highlightNonce, highlightItemId } = useCartStore.getState();
    if (highlightNonce === nonceBefore || !highlightItemId) return;
    requestCustomRate(highlightItemId, rate, includesTax);
  }, [handleAddToCart, requestCustomRate]);

  const handleItemKeyDown = useCallback((index: number, item: MenuItem, e: React.KeyboardEvent) => {
    if (pricePopup && pricePopup.rowIndex === index) {
      // Several keys here (Backspace, Escape, digits) are also bound by
      // document-level global shortcuts (e.g. Backspace -> jump to search).
      // preventDefault alone only blocks the browser's own default action, not
      // other addEventListener('keydown', ...) listeners further up the DOM -
      // stopPropagation is what actually keeps this modal-like popup from
      // leaking keys to them.
      e.stopPropagation();
      const currentOption = pricePopup.options[pricePopup.selectedIndex];
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const direction = e.key === 'ArrowDown' ? 1 : -1;
        setPricePopup((p) => {
          if (!p) return p;
          const nextIndex = cyclePriceOptionIndex(p.selectedIndex, p.options.length, direction);
          const nextOption = p.options[nextIndex];
          // Re-seed on arrival so the field always shows this option's own
          // rate, not whatever was last typed while a different option (or
          // none) was selected.
          return {
            ...p,
            selectedIndex: nextIndex,
            customValue: nextOption?.isCustom ? String(nextOption.rate) : p.customValue,
          };
        });
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setPricePopup(null);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        const quantity = bufferToQuantity(quantityBuffer);
        setQuantityBuffer('');
        setPricePopup(null);
        if (currentOption?.isCustom) {
          const parsed = parseFloat(pricePopup.customValue);
          // An empty or invalid custom value isn't "free" - it means the
          // cashier didn't actually set a price, so the line keeps whatever
          // rate it already has (mirrors the cart's own Rate field: clearing
          // it removes the override rather than zeroing the price).
          const rate = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
          void commitPriceSelection(item, quantity, rate, isTaxIncludedInBasicRate);
        } else {
          void commitPriceSelection(item, quantity, currentOption?.rate ?? null, false);
        }
        return;
      }
      if (currentOption?.isCustom) {
        if (/^[0-9.]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
          e.preventDefault();
          setPricePopup((p) => {
            if (!p) return p;
            // A single leading zero reads as "still typing the first digit", not a value.
            const base = p.customValue === "0" ? "" : p.customValue;
            if (e.key === '.' && base.includes('.')) return p;
            return { ...p, customValue: base + e.key };
          });
          return;
        }
        if (e.key === 'Backspace') {
          e.preventDefault();
          setPricePopup((p) => p && ({ ...p, customValue: p.customValue.slice(0, -1) }));
          return;
        }
      }
      // Any other key while the popup is open is swallowed rather than falling
      // through to the quantity-buffer/navigation handling below.
      e.preventDefault();
      return;
    }

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
    } else if (e.key === '.') {
      // No match: leave the key unbound (no preventDefault) rather than swallow it.
      const cartItem = cartItems.find(ci => (ci.item_code || ci.id) === (item.item_code || item.id));
      if (!cartItem) return;

      e.preventDefault();
      setQuantityBuffer('');
      const wasExpanded = expandedCartItemId === cartItem.id;
      toggleItemExpansion(cartItem.id);
      // Opening moves focus onto the cart line so it can be worked on there;
      // collapsing an already-open line leaves focus on the item list, where
      // this keypress originated, instead of jumping it to a row that just closed.
      if (!wasExpanded) {
        document.querySelector<HTMLElement>(`[data-cart-item-id="${cartItem.id}"][tabindex]`)?.focus();
      }
    } else if (e.key === '*') {
      e.preventDefault();
      void openPricePopup(index, item);
    }
  }, [cartItems, expandedCartItemId, handleAddToCart, isTaxIncludedInBasicRate, openPricePopup, pricePopup, commitPriceSelection, quantityBuffer, quantityShortcutEnabled, removeItem, toggleItemExpansion, updateQuantity]);

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
          useItemCodeAsName={useItemCodeAsName}
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
        {pricePopup && (
          <PriceListPopup
            options={pricePopup.options}
            selectedIndex={pricePopup.selectedIndex}
            customValue={pricePopup.customValue}
            position={pricePopup.position}
            currencySymbol={posDetails?.currency_symbol}
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
            useItemCodeAsName={useItemCodeAsName}
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
      {pricePopup && (
        <PriceListPopup
          options={pricePopup.options}
          selectedIndex={pricePopup.selectedIndex}
          customValue={pricePopup.customValue}
          position={pricePopup.position}
          currencySymbol={posDetails?.currency_symbol}
        />
      )}
    </>
  );
}
