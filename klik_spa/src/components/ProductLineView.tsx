"use client"

import { Fragment, useCallback, useMemo, useState } from "react"
import type { MenuItem } from "../../types"
import ProductDetailsModal from "./ProductDetailsModal"
import ProductLineRow from "./ProductLineRow"
import { usePOSProfileStore } from "../stores/posProfileStore"
import { groupHeaders, lineViewColumns } from "../utils/lineViewColumns"
import { useProductStore } from "../stores/productStore"


interface ProductLineViewProps {
  items: MenuItem[]
  onAddToCart: (item: MenuItem) => void
  isMobile?: boolean
  scannerOnly?: boolean
  showItemCode?: boolean
  useItemCodeAsName?: boolean
  hideImages?: boolean
  focusedIndex?: number
  onItemFocus?: (index: number) => void
  onItemKeyDown?: (index: number, item: MenuItem, e: React.KeyboardEvent<HTMLDivElement>) => void
  stockUnavailable?: boolean
  lossOfSaleEnabled?: boolean
  quantityBuffer?: string
}

export default function ProductLineView({
  items,
  onAddToCart,
  isMobile = false,
  scannerOnly = false,
  showItemCode = false,
  useItemCodeAsName = false,
  hideImages = false,
  focusedIndex = -1,
  onItemFocus,
  onItemKeyDown,
  stockUnavailable = false,
  lossOfSaleEnabled = false,
  quantityBuffer = "",
}: ProductLineViewProps) {
  const [selectedItem, setSelectedItem] = useState<MenuItem | null>(null)
  const [showDetailsModal, setShowDetailsModal] = useState(false)

  const { posDetails } = usePOSProfileStore()
  const showCostColumn = !(posDetails?.restrict_cost_visibility_in_tooltip ?? true)
  const selectedCategory = useProductStore((s) => s.selectedCategory)
  const searching = useProductStore((s) => s.searchQuery.trim() !== "")
  const headers = useMemo(
    () => groupHeaders(items.map((item) => item.category), { searching, selectedCategory }),
    [items, searching, selectedCategory],
  )
  const columns = lineViewColumns({ showItemCode, showCost: showCostColumn })

  const handleInfoClick = useCallback((item: MenuItem) => {
    setSelectedItem(item)
    setShowDetailsModal(true)
  }, [])

  const handleModalClose = () => {
    setShowDetailsModal(false)
    setSelectedItem(null)
  }

  if (items.length === 0) {
    return (
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
    )
  }
  

  return (
    <>
      <div className={`${isMobile ? "p-4" : "p-1"} bg-gray-50 dark:bg-gray-900`}>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 mb-2 overflow-visible">
          {!isMobile && (
            <div className="grid grid-cols-12 gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-700 border-b">
              {columns.code && (
                <div className={`${columns.code} text-xs font-semibold text-gray-900 dark:text-white`}>Item Code</div>
              )}
              <div className={`${columns.name} text-xs font-semibold text-gray-900 dark:text-white`}>
                {/* Below xl the code sits under the name, in this one column. */}
                {columns.code ? <><span className="xl:hidden">Product</span><span className="hidden xl:inline">Item Name</span></> : "Item Name"}
              </div>
              {showCostColumn && (
                <div className="col-span-1 text-xs font-semibold text-right text-gray-400 dark:text-gray-500">Cost</div>
              )}
              <div className="col-span-2 text-xs font-semibold text-right text-gray-900 dark:text-white">Rate</div>
              <div className="col-span-2 text-xs font-semibold text-right text-gray-900 dark:text-white">Qty</div>
              <div className="col-span-1 text-xs font-semibold text-center text-gray-900 dark:text-white">UOM</div>
              <div className="col-span-1 text-xs font-semibold text-center text-gray-900 dark:text-white">Action</div>
            </div>
          )}

          <div className="divide-y divide-gray-200 dark:divide-gray-600">
            {items.map((item, rowIndex) => (
              <Fragment key={item.id}>
              {headers.has(rowIndex) && (
                // Sticks to the top while its group scrolls by; the next group's header
                // slides over it.
                <div className="sticky top-0 z-10 px-3 py-1 bg-gray-100 dark:bg-gray-700 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-300">
                  {headers.get(rowIndex)}
                </div>
              )}
              <ProductLineRow
                item={item}
                rowIndex={rowIndex}
                isFocused={focusedIndex === rowIndex}
                quantityBuffer={focusedIndex === rowIndex ? quantityBuffer : ""}
                isMobile={isMobile}
                scannerOnly={scannerOnly}
                showItemCode={showItemCode}
                useItemCodeAsName={useItemCodeAsName}
                hideImages={hideImages}
                stockUnavailable={stockUnavailable}
                lossOfSaleEnabled={lossOfSaleEnabled}
                showCostColumn={showCostColumn}
                columns={columns}
                onAddToCart={onAddToCart}
                onItemFocus={onItemFocus}
                onItemKeyDown={onItemKeyDown}
                onInfoClick={handleInfoClick}
              />
              </Fragment>
            ))}
          </div>
        </div>
      </div>

      {showDetailsModal && selectedItem && (
        <ProductDetailsModal
          item={selectedItem}
          onClose={handleModalClose}
        />
      )}
    </>
  )
}
