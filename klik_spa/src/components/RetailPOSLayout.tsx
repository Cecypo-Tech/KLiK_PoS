"use client";

import { useState, useEffect, useCallback } from "react";
import { useCartStore } from "../stores/cartStore";
import MenuGrid from "./MenuGrid";
import OrderSummary from "./order/OrderSummary";
import MobilePOSLayout from "./MobilePOSLayout";
import LoadingSpinner from "./LoadingSpinner";
import BarcodeScannerModal from "./BarcodeScanner";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useProduct } from "../providers/ProductProvider";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { scanAdd } from "../utils/lineGridSearch";
import { toast } from "react-toastify";

export default function RetailPOSLayout() {
  const [showScanner, setShowScanner] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const isMobile = useMediaQuery("(max-width: 1024px)");
  // Grid tills keep the grid down to 768 px (an 800x600 counter screen); below that, the phone layout.
  const isPhone = useMediaQuery("(max-width: 767px)");
  
  const {
    error: productError,
    filteredItems,
    useScannerOnly,
    searchQuery,
    hasMore,
    isLoadingMore,
    loadMoreProducts,
    totalCount,
    isSearching,
    searchProducts,
    setCategory,
    selectedCategory,
    refreshStockOnly,
  } = useProduct();

  const { 
    fetchPOSDetails, 
    posDetails,
    clearCache,
  } = usePOSProfileStore();

  const { clearCart } = useCartStore();

  useEffect(() => {
    const handleBeforeUnload = () => {
      clearCache();
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [clearCache]);

  useEffect(() => {
    const init = async () => {
      await fetchPOSDetails(true);
      setIsInitializing(false);
    };

    init();
  }, []);

  const handleSearchInput = useCallback((query: string) => {
    searchProducts(query);
  }, [searchProducts]);

  const isGrid = posDetails?.custom_default_view === "Line Entry View" && !isPhone;

  const handleBarcodeDetected = useCallback((barcode: string) => {
    setShowScanner(false);
    if (!isGrid) {
      searchProducts(barcode, true);
      return;
    }
    // Grid tills: a camera scan adds like a scanner scan into the entry row.
    scanAdd(barcode)
      .then((r) => {
        if ("pick" in r) toast.info(`${r.pick.name} has variants: type it in the entry row to pick one`);
      })
      .catch((e) => {
        console.error("Camera scan failed:", e);
        toast.error(`Lookup for ${barcode} failed`);
      });
  }, [searchProducts, isGrid]);

  const handleCategoryChange = useCallback((category: string) => {
    setCategory(category);
  }, [setCategory]);

  const handleRefreshStock = useCallback(() => {
    refreshStockOnly();
  }, [refreshStockOnly]);

  useEffect(() => {
    const handleFocus = () => {
      refreshStockOnly();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshStockOnly]);

  if (isInitializing && !posDetails) {
    return <LoadingSpinner message="Loading POS configuration..." />;
  }

  if (productError && filteredItems.length === 0 && !isSearching) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center p-8">
          <div className="text-red-500 mb-4">
            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-800 mb-2">Failed to Load POS</h2>
          <p className="text-gray-600 mb-4">{productError}</p>
          <button
            onClick={() => window.location.reload()}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (isMobile && !isGrid) {
    return (
      <>
        <MobilePOSLayout
          items={filteredItems}
          selectedCategory={selectedCategory}
          onCategoryChange={handleCategoryChange}
          searchQuery={searchQuery}
          onSearchChange={handleSearchInput}
          onScanBarcode={() => setShowScanner(true)}
          scannerOnly={useScannerOnly}
          hasMore={hasMore && !searchQuery}
          isLoadingMore={isLoadingMore}
          onLoadMore={loadMoreProducts}
          totalCount={totalCount}
          isSearching={isSearching}
        />
        <BarcodeScannerModal
          isOpen={showScanner}
          onClose={() => setShowScanner(false)}
          onBarcodeDetected={handleBarcodeDetected}
        />
      </>
    );
  }

  return (
    <>
      {isGrid ? (
        <div className="flex h-screen bg-gray-50 dark:bg-gray-900 pb-2">
          <div className="flex-1 overflow-hidden ml-20 flex flex-col">
            <MenuGrid headerOnly onRefreshStock={handleRefreshStock} onScanBarcode={() => setShowScanner(true)} />
            <div className="flex-1 min-h-0">
              <OrderSummary layout="grid" onClearCart={clearCart} />
            </div>
          </div>
        </div>
      ) : (
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 pb-2">
        <div className="flex-1 overflow-hidden ml-20">
          <MenuGrid
            onRefreshStock={handleRefreshStock}
            onScanBarcode={() => setShowScanner(true)}
          />
        </div>

        <div className="w-[35%] min-w-[420px] max-w-[600px] bg-white shadow-lg overflow-y-auto">
          <OrderSummary onClearCart={clearCart} />
        </div>
      </div>
      )}

      <BarcodeScannerModal
        isOpen={showScanner}
        onClose={() => setShowScanner(false)}
        onBarcodeDetected={handleBarcodeDetected}
      />
    </>
  );
}