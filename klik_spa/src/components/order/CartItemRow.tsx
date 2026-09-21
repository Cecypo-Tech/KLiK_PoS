"use client";

import { useState, useEffect, useCallback } from "react";
import { Minus, Plus, X, Package, ChevronDown, ChevronUp, AlertTriangle, Eye, Pencil } from "lucide-react";
import { toast } from "react-toastify";
import type { BundleEntry, CartItem, ItemTaxInfo } from "../../../types";
import { QuantityInput } from "./QuantityInput";
import { formatCurrencyWithSymbol } from "../../utils/currency";
import { UOMSelectField } from "./UOMSelectField";
import { SerialBatchBundleModal } from "./SerialBatchBundleSelector";
import { useCartStore } from "../../stores/cartStore";
import ProductDetailsModal from "../ProductDetailsModal";
import DescriptionDialog from "./DescriptionDialog";
import { CART_ROW_GRID } from "./cartTableLayout";
import { getEffectiveDisplayRate, getEffectiveItemRate, getExclusiveTaxRateForItem } from "../../utils/cartPricing";
import { roundCurrency } from "../../utils/currencyMath";
import { getItemDisplayName } from "../../utils/itemDisplayName";
import { getCostMargin, getInclusiveTaxRate } from "../../utils/costMargin";

interface CartItemRowProps {
  item: CartItem;
  itemId: string;
  isExpanded: boolean;
  onToggleExpand: () => void;
  itemDiscount: any;
  onUpdateQuantity: (id: string, quantity: number) => void;
  onRemoveItem?: (id: string) => void;
  onUOMChange: (itemId: string, uom: string, price: number, conversionFactor?: number) => void;
  onDescriptionChange?: (itemId: string, description: string) => void;
  onDiscountChange: (itemId: string, field: string, value: number | string) => void;
  onCustomRateChange: (item: CartItem, rate?: number, includesTax?: boolean) => void;
  onDuplicateItem: (item: CartItem) => void;
  onBundleUpdate?: (itemId: string, bundleId: string, entries: any[]) => void;
  selectedCustomer?: { id: string } | null;
  posDetails: any;
  itemBatches: any[];
  itemSerials: string[];
  currency_symbol?: string;
  isMobile?: boolean;
  autoFetchBatch?: boolean;
}

interface BatchData {
  batch_no: string;
  qty: number;
  expiry_date: string;
  manufacturing_date: string;
}

interface SerialData {
  serial_no: string;
}

interface PriceListEntry {
  price_list: string;
  rate: number;
  currency: string;
  uom?: string;
  customer?: string;
  note?: string;
  cost: number;
  margin: number;
  margin_pct: number;
}

interface WarehouseStock {
  warehouse: string;
  bal_qty: number;
  val_rate: number;
}

interface ItemFullData {
  item_name: string;
  item_code: string;
  standard_rate: number;
  valuation_rate: number;
  price_lists: PriceListEntry[];
  batches: BatchData[];
  serials: SerialData[];
  warehouse_stock: WarehouseStock[];
  uom: string;
  brand?: string;
  has_batch_no: number;
  has_serial_no: number;
  total_bal_qty: number;
  global_stock_total?: {
    total_qty: number;
    total_value: number;
    avg_valuation_rate: number;
  };
}

export const CartItemRow = ({
  item,
  itemId,
  isExpanded,
  onToggleExpand,
  itemDiscount,
  onUpdateQuantity,
  onRemoveItem,
  onUOMChange,
  onDiscountChange,
  onCustomRateChange,
  onDuplicateItem,
  onBundleUpdate,
  onDescriptionChange,
  selectedCustomer,
  posDetails,
  currency_symbol,
  isMobile,
  autoFetchBatch = false,
}: CartItemRowProps) => {
  const { updateItemBundleEntries, adjustQuantity } = useCartStore();
  const highlightItemId = useCartStore((s) => s.highlightItemId);
  const highlightNonce = useCartStore((s) => s.highlightNonce);
  const [glowing, setGlowing] = useState(false);

  useEffect(() => {
    if (highlightItemId !== item.id) {
      // Highlight moved to another item (or cleared) — make sure this row
      // never stays stuck glowing, even on rapid successive clicks.
      setGlowing(false);
      return;
    }
    setGlowing(true);
    const t = setTimeout(() => setGlowing(false), 1200);
    return () => clearTimeout(t);
  }, [highlightItemId, highlightNonce, item.id]);
  const [showBundleModal, setShowBundleModal] = useState(false);
  const [isBundleDetailsOpen, setIsBundleDetailsOpen] = useState(false);
  const [showProductModal, setShowProductModal] = useState(false);
  const [showDescriptionDialog, setShowDescriptionDialog] = useState(false);
  const [bundleEntries, setBundleEntries] = useState<BundleEntry[]>(() => {
    if (item.bundle_entries && Array.isArray(item.bundle_entries)) {
      return item.bundle_entries;
    }
    if (itemDiscount.bundle_entries && typeof itemDiscount.bundle_entries === "string") {
      try {
        return JSON.parse(itemDiscount.bundle_entries);
      } catch {
        return [];
      }
    }
    return [];
  });
  const [availableBatches, setAvailableBatches] = useState<BatchData[]>([]);
  const [availableSerials, setAvailableSerials] = useState<SerialData[]>([]);
  const [isFetchingBundleData, setIsFetchingBundleData] = useState(false);
  const [modalEntries, setModalEntries] = useState<BundleEntry[]>([]);
  const [modalQty, setModalQty] = useState(item.quantity);
  const [localQty, setLocalQty] = useState(item.quantity);
  const [isRateEditing, setIsRateEditing] = useState(false);
  const [rateInputValue, setRateInputValue] = useState("");

  useEffect(() => {
    setLocalQty(item.quantity);
  }, [item.quantity]);
  const [localDiscountPct, setLocalDiscountPct] = useState<number>(() => {
    const amt = itemDiscount.discountAmount || 0;
    return item.price > 0 ? parseFloat(((amt / item.price) * 100).toFixed(2)) : 0;
  });

  useEffect(() => {
    const amt = itemDiscount.discountAmount || 0;
    const nextDiscountPct = item.price > 0 ? parseFloat(((amt / item.price) * 100).toFixed(2)) : 0;
    setLocalDiscountPct(nextDiscountPct);
  }, [itemDiscount.discountAmount, item.price]);
  const [fullItemData, setFullItemData] = useState<ItemFullData | null>(null);
  const [isLoadingFullData, setIsLoadingFullData] = useState(false);

  const hasSerialOrBatch = item.has_serial_no || item.has_batch_no;
  const warehouse = posDetails?.warehouse || "";
  const restrictCostVisibility = posDetails?.restrict_cost_visibility_in_tooltip ?? true;
  const allowPriceListSwitching = !!posDetails?.allow_price_list_switching;
  const quickSwitchPrice = !!posDetails?.custom_quick_switch_price;

  const fetchFullItemDetails = useCallback(async () => {
    if (!warehouse) return;
    setIsLoadingFullData(true);
    try {
      const response = await fetch(
        `/api/method/klik_pos.api.item.item_details.get_full_pricing_and_batch_details?item_code=${encodeURIComponent(item.item_code || item.id)}&warehouse=${encodeURIComponent(warehouse)}`
      );
      const res = await response.json();
      if (res?.message) {
        setFullItemData(res.message);
      }
    } catch (error) {
      console.error("Failed to fetch full item details:", error);
    } finally {
      setIsLoadingFullData(false);
    }
  }, [item.item_code, item.id, warehouse]);

  useEffect(() => {
    if ((isExpanded || quickSwitchPrice) && warehouse) {
      fetchFullItemDetails();
    }
  }, [isExpanded, quickSwitchPrice, warehouse, fetchFullItemDetails]);

  const saveToCart = useCallback((entries: BundleEntry[]) => {
    const validEntries = entries.map(({ selected, ...e }) => e);
    setBundleEntries(validEntries);
    updateItemBundleEntries(item.id, validEntries);
    if (onBundleUpdate) {
      onBundleUpdate(item.id, "", validEntries);
    }
  }, [item.id, updateItemBundleEntries, onBundleUpdate]);

  const fetchBundleData = useCallback(async (qty: number, shouldSaveToCart: boolean = false) => {
    if (!warehouse) return;
    if (!item.has_serial_no && !item.has_batch_no) return;

    setIsFetchingBundleData(true);
    try {
      const params = new URLSearchParams({
        item_code: item.item_code || item.id,
        warehouse: warehouse,
        customer: selectedCustomer?.id || "",
        qty: qty.toString(),
        based_on: "FIFO",
        has_serial_no: item.has_serial_no ? "1" : "0",
        has_batch_no: item.has_batch_no ? "1" : "0",
      });

      const response = await fetch(`/api/method/klik_pos.api.item.bundle.get_available_batches_and_serials?${params.toString()}`);
      const result = await response.json();

      if (result.message) {
        const data = result.message;
        if (data.batches && Array.isArray(data.batches)) {
          setAvailableBatches(data.batches);
        } else {
          setAvailableBatches([]);
        }
        if (data.serials && Array.isArray(data.serials)) {
          setAvailableSerials(data.serials);
        } else {
          setAvailableSerials([]);
        }
      }

      if (qty > 0) {
        const autoDataResponse = await fetch(`/api/method/erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_auto_data?${params.toString()}`);
        const autoDataResult = await autoDataResponse.json();

        if (autoDataResult.message && Array.isArray(autoDataResult.message) && autoDataResult.message.length > 0) {
          const autoEntries = autoDataResult.message.map((row: any) => ({
            serial_no: row.serial_no || undefined,
            batch_no: row.batch_no || undefined,
            warehouse: row.warehouse || posDetails.warehouse || "",
            qty: row.qty || 1,
            selected: false,
          }));
          setModalEntries(autoEntries);
          if (shouldSaveToCart) {
            saveToCart(autoEntries);
          }
        } else {
          setModalEntries([{
            qty: 1,
            selected: false,
            serial_no: item.has_serial_no ? "" : undefined,
            batch_no: item.has_batch_no ? "" : undefined,
            warehouse: posDetails.warehouse || "",
          }]);
          if (shouldSaveToCart) {
            saveToCart([]);
          }
        }
      }
    } catch (error) {
      console.error("Failed to fetch bundle data:", error);
      toast.error("Failed to fetch batch/serial data");
    } finally {
      setIsFetchingBundleData(false);
    }
  }, [item, warehouse, selectedCustomer, saveToCart]);

  useEffect(() => {
    if (hasSerialOrBatch && warehouse && autoFetchBatch && item.quantity > 0) {
      fetchBundleData(item.quantity, true);
    }
  }, [item.quantity, warehouse, autoFetchBatch, hasSerialOrBatch]);

  useEffect(() => {
    if (bundleEntries.length > 0 && !autoFetchBatch) {
      setModalEntries(bundleEntries);
    }
  }, [bundleEntries, autoFetchBatch]);

  const handleOpenModal = () => {
    if (hasSerialOrBatch) {
      setModalQty(item.quantity);
      if (!autoFetchBatch && item.quantity > 0) {
        fetchBundleData(item.quantity, false);
      } else if (autoFetchBatch && bundleEntries.length === 0 && item.quantity > 0) {
        fetchBundleData(item.quantity, true);
      }
      setShowBundleModal(true);
    }
  };

  const handleBundleSave = (entries: BundleEntry[]) => {
    if (!Array.isArray(entries)) {
      toast.error("Invalid bundle entries");
      return;
    }
    
    const totalBundleQty = entries.reduce((sum, entry) => sum + (Number(entry.qty) || 0), 0);
    
    if (totalBundleQty !== item.quantity) {
      onUpdateQuantity(item.id, totalBundleQty);
    }
    
    saveToCart(entries);
    setShowBundleModal(false);
  };

  const handleModalQtyChange = async (newQty: number) => {
    setModalQty(newQty);
    if (autoFetchBatch && newQty > 0) {
      await fetchBundleData(newQty, true);
    }
  };

  const handleModalFetchData = async (qty: number) => {
    await fetchBundleData(qty, true);
  };

  const isTaxIncludedInBasicRate =
    posDetails?.is_tax_included_in_basic_rate === 1
    || posDetails?.is_tax_included_in_basic_rate === "1"
    || posDetails?.is_tax_included_in_basic_rate === true;

  const handleRateChange = (value?: number) => {
    if (value === undefined || value === null || Number.isNaN(value)) {
      onCustomRateChange(item, undefined);
      onDiscountChange(item.id, "discountAmount", 0);
      setLocalDiscountPct(0);
      return;
    }

    const rate = Math.max(0, value);
    onCustomRateChange(item, rate, isTaxIncludedInBasicRate);
    onDiscountChange(item.id, "discountAmount", 0);
    setLocalDiscountPct(0);
  };

  const handleDiscountPercentageChange = (value: number) => {
    const pct = Math.min(100, Math.max(0, value || 0));
    const amt = parseFloat(((item.price * pct) / 100).toFixed(2));
    setLocalDiscountPct(pct);
    onDiscountChange(item.id, "discountAmount", amt);
  };

  const handleDiscountAmountChange = (value: number) => {
    const amt = Math.max(0, value || 0);
    onDiscountChange(item.id, "discountAmount", amt);
    setLocalDiscountPct(item.price > 0 ? parseFloat(((amt / item.price) * 100).toFixed(2)) : 0);
  };

  const handleLinePriceListChange = (priceListName: string) => {
    onDiscountChange(item.id, "selectedPriceList", priceListName);
    if (!priceListName) {
      handleRateChange(undefined);
      return;
    }

    const matchingPrice = fullItemData?.price_lists?.find((priceList) =>
      priceList.price_list === priceListName
      && (!priceList.uom || priceList.uom === item.uom)
    ) || fullItemData?.price_lists?.find((priceList) => priceList.price_list === priceListName);

    if (matchingPrice) {
      onCustomRateChange(item, Number(matchingPrice.rate || 0), false);
      onDiscountChange(item.id, "discountAmount", 0);
      setLocalDiscountPct(0);
    }
  };

  const discountedPrice = getEffectiveItemRate(item, {
    itemDiscounts: { [item.id]: itemDiscount },
    isTaxIncludedInBasicRate,
  });
  const displayRateInclTax = getEffectiveDisplayRate(item, {
    itemDiscounts: { [item.id]: itemDiscount },
    isTaxIncludedInBasicRate,
  });
  const exclusiveTaxRate = getExclusiveTaxRateForItem(item, { isTaxIncludedInBasicRate });
  const hasExclusiveTax = exclusiveTaxRate > 0;
  const totalTaxRate = hasExclusiveTax ? exclusiveTaxRate : Number(item.total_tax_rate || 0);
  const taxAmountPerUnit = roundCurrency(Math.max(0, displayRateInclTax - discountedPrice));
  // original_price is the rate before any rule discount; price is what it costs now.
  // Reading item.price here showed no strike-through at all once rule discounts stopped
  // being replayed through itemDiscounts.
  const listRate = Number((item as CartItem & { original_price?: number }).original_price || 0) || item.price;
  const originalTotal = roundCurrency(Math.max(listRate, discountedPrice) * item.quantity);
  // ERPNext convention: line displays the price-list (net) rate; tax shows in totals.
  const discountedTotal = roundCurrency(discountedPrice * item.quantity);
  const amount = discountedTotal;
  const editableRate = hasExclusiveTax ? discountedPrice : displayRateInclTax;
  const displayRate = editableRate > 0 ? editableRate : "";

  const hasBundleEntries = bundleEntries.length > 0;

  const currentWarehouseStock = fullItemData?.warehouse_stock?.find(wh => wh.warehouse === warehouse);
  const availableStock = currentWarehouseStock?.bal_qty || 0;
  const valuationRate = typeof currentWarehouseStock?.val_rate === "number" ? currentWarehouseStock.val_rate : null;
  // val_rate is per stock UOM and never includes sales tax; discountedPrice is per the line's
  // UOM and includes whatever tax is baked into the rate. The list's tax_info (carried onto the
  // cart item) knows the POS Profile's tax template too; a line restored without it falls back
  // to the cart's own tax fields, which only see an Item Tax Template.
  const listTaxInfo = (item as CartItem & { tax_info?: ItemTaxInfo }).tax_info;
  const inclusiveTaxRate = listTaxInfo
    ? getInclusiveTaxRate(listTaxInfo)
    : !hasExclusiveTax ? totalTaxRate : 0;
  const isInclusiveTax = inclusiveTaxRate > 0;
  const hasValidValuationRate = valuationRate !== null && valuationRate > 0;
  const { costInclTax: valuationRateInclTax, margin: lineMargin } = getCostMargin({
    sellPrice: discountedPrice,
    costPerStockUom: valuationRate ?? 0,
    inclusiveTaxRate,
    conversionFactor: item.conversion_factor,
  });
  const isNegativeMargin = hasValidValuationRate ? lineMargin < 0 : false;
  const marginAmount = hasValidValuationRate ? lineMargin : 0;
  const marginPercentage = hasValidValuationRate ? (marginAmount / valuationRateInclTax) * 100 : 0;

  const showPositiveMarginWarning = !restrictCostVisibility && hasValidValuationRate && lineMargin > 0;
  const showNegativeMarginWarning = !restrictCostVisibility && hasValidValuationRate && isNegativeMargin && discountedPrice > 0;
  const showStockWarning = item.quantity > availableStock && availableStock > 0;
  const showNoStockWarning = availableStock === 0;

  return (
    <>
      <div
        data-cart-item-id={itemId}
        className={`transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/40 ${glowing ? "cart-item-glow" : ""}`}
      >
        <div
          data-cart-item-id={itemId}
          tabIndex={0}
          className={`${isMobile ? "px-3 py-2" : "px-3 py-1.5"} cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-beveren-400/50`}
          onClick={onToggleExpand}
          onKeyDown={(e) => {
            if (e.key === "Escape" && isExpanded) {
              e.preventDefault();
              onToggleExpand();
              const el = document.getElementById("pos-search-input") as HTMLInputElement | null;
              el?.focus();
              el?.select();
            }
          }}
        >
          <div className={CART_ROW_GRID}>
            {/* Item: chevron, name, code, actions */}
            {/* The actions sit under the name: beside it they left a narrow cart no room for it. */}
            <div className="min-w-0 grid grid-cols-[0.75rem_minmax(0,1fr)] items-start gap-x-1">
              <svg
                className={`flex-shrink-0 w-3 h-3 mt-1 text-gray-400 dark:text-gray-500 transform transition-transform duration-200 ${
                  isExpanded ? "rotate-90" : ""
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-tight text-gray-900 dark:text-white line-clamp-2 break-words" title={item.name}>
                  {getItemDisplayName(item, !!posDetails?.custom_use_item_code_as_display_name)}
                </p>
                {!!posDetails?.custom_show_item_code_in_product_list && (item.item_code || item.id) && (
                  <p className="text-[11px] text-gray-400 dark:text-gray-500 font-mono leading-tight truncate">
                    {posDetails?.custom_use_item_code_as_display_name ? item.name : (item.item_code || item.id)}
                  </p>
                )}
              </div>
              {/* Quick Switch Price: per-line price-list pills, under the name */}
              {quickSwitchPrice && fullItemData?.price_lists?.length ? (
                <div className="col-start-2 mt-1 flex flex-wrap items-center gap-1">
                  {fullItemData.price_lists
                    .filter((priceList) => (!priceList.uom || priceList.uom === item.uom) && Number(priceList.rate || 0) > 0)
                    .map((priceList) => {
                      const active = itemDiscount.selectedPriceList === priceList.price_list;
                      const shortName =
                        priceList.price_list.length > 8
                          ? priceList.price_list.slice(0, 8)
                          : priceList.price_list;
                      return (
                        <button
                          key={`${priceList.price_list}-${priceList.uom || ""}-${priceList.rate}`}
                          onClick={(e) => { e.stopPropagation(); handleLinePriceListChange(priceList.price_list); }}
                          title={`${priceList.price_list}: ${formatCurrencyWithSymbol(Number(priceList.rate || 0), currency_symbol)}`}
                          className={`flex-shrink-0 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                            active
                              ? "border-beveren-500 bg-beveren-50 text-beveren-700 dark:bg-beveren-900/30 dark:text-beveren-300"
                              : "border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-beveren-300"
                          }`}
                        >
                          <span className="font-mono">{shortName} {Number(priceList.rate || 0).toFixed(2)}</span>
                        </button>
                      );
                    })}
                </div>
              ) : null}
            </div>

            {/* Qty: - qty UOM + */}
            <div className="flex items-center justify-center">
              <div className="flex items-center border border-gray-200 dark:border-gray-600 rounded-full overflow-hidden">
              <button
                onClick={(e) => { e.stopPropagation(); adjustQuantity(item.id, -1); }}
                className={`${
                  isMobile ? "w-7 h-7" : "w-6 h-6"
                } flex items-center justify-center text-gray-400 dark:text-gray-500 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-500 dark:hover:text-red-400 transition-colors`}
                aria-label="Decrease quantity"
              >
                <Minus size={isMobile ? 12 : 10} />
              </button>
              <input
                type="number"
                min="0"
                value={localQty}
                onChange={(e) => setLocalQty(parseInt(e.target.value, 10) || 0)}
                onBlur={() => {
                  const available = item.available;
                  if (available > 0 && localQty > available && !item.allow_negative_stock) {
                    setLocalQty(available);
                    onUpdateQuantity(item.id, available);
                    toast.warning(`Only ${available} units available. Quantity set to ${available}.`);
                  } else {
                    onUpdateQuantity(item.id, localQty);
                  }
                }}
                onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); } }}
                onClick={(e) => (e.target as HTMLInputElement).select()}
                className={`w-7 text-center font-semibold text-gray-900 dark:text-white text-sm border-l border-gray-200 dark:border-gray-600 py-0.5 bg-transparent focus:outline-none focus:bg-gray-50 dark:focus:bg-gray-700 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none`}
              />
              {/* The UOM picker lives in the expanded panel; the label opens it. */}
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onToggleExpand(); }}
                className="max-w-[2.5rem] truncate px-1 text-[10px] font-medium text-gray-500 dark:text-gray-400 border-r border-gray-200 dark:border-gray-600 hover:text-beveren-600 dark:hover:text-beveren-400"
                title={item.uom ? `Unit: ${item.uom}` : "Change unit"}
              >
                {item.uom || "Nos"}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); adjustQuantity(item.id, 1); }}
                className={`${
                  isMobile ? "w-7 h-7" : "w-6 h-6"
                } flex items-center justify-center text-gray-400 dark:text-gray-500 hover:bg-green-50 dark:hover:bg-green-900/30 hover:text-green-600 dark:hover:text-green-400 transition-colors`}
                aria-label="Increase quantity"
              >
                <Plus size={isMobile ? 12 : 10} />
              </button>
              </div>
            </div>

            {/* Rate */}
            <p className="text-right text-xs text-gray-500 dark:text-gray-400 tabular-nums whitespace-nowrap">
              {formatCurrencyWithSymbol(discountedPrice, currency_symbol)}
            </p>

            {/* Total */}
            <div className="text-right tabular-nums">
              {discountedTotal !== originalTotal ? (
                <p className="text-[10px] leading-tight text-gray-400 dark:text-gray-500 line-through whitespace-nowrap">
                  {formatCurrencyWithSymbol(originalTotal, currency_symbol)}
                </p>
              ) : null}
              <p
                className={`text-beveren-600 dark:text-beveren-400 font-semibold whitespace-nowrap ${
                  isMobile ? "text-sm" : "text-sm"
                }`}
              >
                {formatCurrencyWithSymbol(discountedTotal !== originalTotal ? discountedTotal : amount, currency_symbol)}
              </p>
              {/* Line actions, far right under the total: edit description, details, remove. */}
              <div className="mt-0.5 -mr-1 flex items-center justify-end">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowDescriptionDialog(true); }}
                  className={`${isMobile ? "w-7 h-7" : "w-5 h-5"} rounded flex items-center justify-center text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200 transition-colors`}
                  title="Edit description"
                  aria-label="Edit description"
                >
                  <Pencil size={isMobile ? 13 : 11} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setShowProductModal(true); }}
                  className={`${isMobile ? "w-7 h-7" : "w-5 h-5"} rounded flex items-center justify-center text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200 transition-colors`}
                  title="View full details"
                  aria-label="View full details"
                >
                  <Eye size={isMobile ? 14 : 12} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onRemoveItem?.(item.id); }}
                  className={`${isMobile ? "w-7 h-7" : "w-5 h-5"} rounded flex items-center justify-center text-gray-400 dark:text-gray-500 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-colors`}
                  title="Remove item"
                  aria-label="Remove item"
                >
                  <X size={isMobile ? 15 : 13} />
                </button>
              </div>
            </div>
          </div>
        </div>

        {isExpanded ? (
          <div
            className="border-t border-gray-200 dark:border-gray-700 px-3 py-2 bg-gray-50 dark:bg-gray-900/30"
          >
            <div className="w-full">
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    Quantity
                  </label>
                  <QuantityInput
                    item={item}
                    onUpdateQuantity={onUpdateQuantity}
                    isMobile={isMobile}
                  />
                </div>
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    UOM
                  </label>
                  <UOMSelectField
                    item={item}
                    onUOMChange={onUOMChange}
                    isMobile={isMobile}
                    selectedCustomer={selectedCustomer}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    {hasExclusiveTax ? "Rate (Excl. Tax)" : "Rate (Incl. Tax)"}
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={isRateEditing ? rateInputValue : displayRate}
                    onFocus={() => {
                      setIsRateEditing(true);
                      setRateInputValue(String(displayRate));
                    }}
                    onBlur={() => {
                      setIsRateEditing(false);
                      setRateInputValue("");
                    }}
                    onChange={(e) => {
                      const value = e.target.value.trim();
                      setRateInputValue(value);

                      if (value === "") {
                        handleRateChange(undefined);
                        return;
                      }

                      const parsedValue = parseFloat(value);
                      handleRateChange(Number.isNaN(parsedValue) ? undefined : parsedValue);
                    }}
                    readOnly={!posDetails?.allow_rate_change}
                    placeholder="0"
                    className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-beveren-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${
                      showNegativeMarginWarning ? "border-red-300 dark:border-red-600" : showPositiveMarginWarning ? "border-blue-300 dark:border-blue-600" : ""
                    }`}
                  />
                </div>
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    {hasExclusiveTax ? "Amount (Excl. Tax)" : "Amount (Incl. Tax)"}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={amount}
                    readOnly
                    className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white cursor-not-allowed`}
                  />
                </div>
              </div>

              {totalTaxRate > 0 && (
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                      Tax Rate
                    </label>
                    <input
                      type="text"
                      value={`${totalTaxRate.toFixed(2)}%`}
                      readOnly
                      className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white cursor-not-allowed`}
                    />
                  </div>
                  <div>
                    <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                      {hasExclusiveTax ? "Rate (Incl. Tax)" : "Base Rate"}
                    </label>
                    <input
                      type="text"
                      value={formatCurrencyWithSymbol(hasExclusiveTax ? displayRateInclTax : discountedPrice, currency_symbol)}
                      readOnly
                      className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white cursor-not-allowed`}
                    />
                  </div>
                  {hasExclusiveTax && taxAmountPerUnit > 0 && (
                    <div className="col-span-2 text-xs text-gray-500 dark:text-gray-400">
                      Tax per unit: {formatCurrencyWithSymbol(taxAmountPerUnit, currency_symbol)}
                    </div>
                  )}
                </div>
              )}

              {/* With quick-switch pills on, the pills under the row are the price list selector. */}
              {allowPriceListSwitching && !quickSwitchPrice && fullItemData?.price_lists?.length ? (
                <div className="mb-4">
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    Item Price List
                  </label>
                  <select
                    value={itemDiscount.selectedPriceList || ""}
                    onChange={(event) => handleLinePriceListChange(event.target.value)}
                    disabled={!posDetails?.allow_rate_change}
                    className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-3 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-beveren-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:opacity-60`}
                  >
                    <option value="">Use order price list</option>
                    {fullItemData.price_lists
                      .filter((priceList) => !priceList.uom || priceList.uom === item.uom)
                      .map((priceList) => (
                        <option key={`${priceList.price_list}-${priceList.uom || ""}-${priceList.rate}`} value={priceList.price_list}>
                          {priceList.price_list}
                        </option>
                      ))}
                  </select>
                </div>
              ) : null}

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    Discount Amount
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={itemDiscount.discountAmount || ""}
                    onChange={(e) => handleDiscountAmountChange(parseFloat(e.target.value) || 0)}
                    readOnly={!posDetails?.allow_discount_change}
                    placeholder="0.00"
                    className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-beveren-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-white`}
                  />
                </div>
                <div>
                  <label className={`block text-gray-700 dark:text-gray-300 font-medium ${isMobile ? "text-sm" : "text-sm"} mb-2`}>
                    Discount (%)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={localDiscountPct || ""}
                    onChange={(e) => handleDiscountPercentageChange(parseFloat(e.target.value) || 0)}
                    readOnly={!posDetails?.allow_discount_change}
                    placeholder="0.0"
                    className={`w-full ${isMobile ? "text-sm" : "text-sm"} px-3 py-4 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-beveren-500 focus:border-transparent bg-white dark:bg-gray-800 text-gray-900 dark:text-white`}
                  />
                </div>
              </div>

              {hasSerialOrBatch ? (
                <div className="mb-4">
                  <button
                    onClick={handleOpenModal}
                    className={`w-full flex items-center justify-center gap-2 px-3 py-4 rounded-md border ${
                      hasBundleEntries
                        ? "border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/30"
                        : "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30"
                    } transition-colors ${isMobile ? "text-sm" : "text-sm"} font-medium`}
                  >
                    <Package size={isMobile ? 16 : 14} />
                    {hasBundleEntries ? "Update Serial/Batch" : "Add Serial/Batch"}
                  </button>
                </div>
              ) : (
                <></>
              )}

              {hasBundleEntries ? (
                <div className="mt-3 rounded-md border border-blue-200 dark:border-blue-800 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setIsBundleDetailsOpen(!isBundleDetailsOpen)}
                    className="w-full flex items-center justify-between p-2 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                  >
                    <span className="text-xs text-blue-800 dark:text-blue-300 font-medium">
                      Batch/Serial Details:
                    </span>
                    {isBundleDetailsOpen ? (
                      <ChevronUp size={14} className="text-blue-800 dark:text-blue-300" />
                    ) : (
                      <ChevronDown size={14} className="text-blue-800 dark:text-blue-300" />
                    )}
                  </button>
                  {isBundleDetailsOpen ? (
                    <div className="p-2 pt-0 bg-blue-50 dark:bg-blue-900/20 space-y-1">
                      {bundleEntries.map((entry, idx) => (
                        <div key={idx} className="text-xs text-blue-700 dark:text-blue-400">
                          {entry.serial_no ? <span>Serial: {entry.serial_no} </span> : <></>}
                          {entry.batch_no ? <span>Batch: {entry.batch_no} </span> : <></>}
                          {entry.qty ? <span>Qty: {entry.qty}</span> : <></>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <></>
                  )}
                </div>
              ) : (
                <></>
              )}


            {isLoadingFullData ? (
              <div className="flex items-center justify-center py-4 mt-3">
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-beveren-500 border-t-transparent" />
                <span className="ml-2 text-xs text-gray-500">Loading details...</span>
              </div>
            ) : (
              <div className="space-y-3 mt-3">
                {showNoStockWarning ? (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-md border border-red-200 dark:border-red-800 flex items-center gap-2">
                    <AlertTriangle size={16} className="text-red-600 dark:text-red-400" />
                    <span className="text-xs text-red-700 dark:text-red-300">
                      No stock available in {warehouse}
                    </span>
                  </div>
                ) : showStockWarning ? (
                  <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-md border border-yellow-200 dark:border-yellow-800 flex items-center gap-2">
                    <AlertTriangle size={16} className="text-yellow-600 dark:text-yellow-400" />
                    <span className="text-xs text-yellow-700 dark:text-yellow-300">
                      Only {availableStock} units available in {warehouse}
                    </span>
                  </div>
                ) : null}

                {currentWarehouseStock && (
                  <div className={`grid gap-3 ${(showPositiveMarginWarning || showNegativeMarginWarning) ? "grid-cols-3" : "grid-cols-2"}`}>
                    <div className="bg-gray-50 dark:bg-gray-700/40 rounded-md p-3 border border-gray-200 dark:border-gray-600">
                      <p className="text-[10px] text-gray-400 uppercase font-semibold">Stock Balance</p>
                      <p className="text-base font-bold text-gray-900 dark:text-white">
                        {currentWarehouseStock.bal_qty.toLocaleString()} {fullItemData?.uom}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-1">in {warehouse}</p>
                    </div>
                    {!restrictCostVisibility && (
                      <div className="bg-gray-50 dark:bg-gray-700/40 rounded-md p-3 border border-gray-200 dark:border-gray-600">
                        <p className="text-[10px] text-gray-400 uppercase font-semibold">Valuation Rate{isInclusiveTax ? " (excl. VAT)" : ""}</p>
                        <p className="text-base font-bold text-gray-900 dark:text-white">
                          {formatCurrencyWithSymbol(currentWarehouseStock.val_rate, currency_symbol)}
                        </p>
                        <p className="text-[10px] text-gray-500 mt-1">per {fullItemData?.uom}</p>
                      </div>
                    )}
                    {showPositiveMarginWarning && (
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-md p-3 border border-blue-200 dark:border-blue-800">
                        <p className="text-[10px] text-blue-500 dark:text-blue-400 uppercase font-semibold">Margin{isInclusiveTax ? " (cost incl. VAT)" : ""}</p>
                        <p className="text-base font-bold text-green-600 dark:text-green-400">
                          +{formatCurrencyWithSymbol(marginAmount, currency_symbol)}
                        </p>
                        <p className="text-[10px] text-green-600 dark:text-green-400 mt-1">{marginPercentage.toFixed(1)}%</p>
                      </div>
                    )}
                    {showNegativeMarginWarning && (
                      <div className="bg-red-50 dark:bg-red-900/20 rounded-md p-3 border border-red-200 dark:border-red-800">
                        <p className="text-[10px] text-red-500 dark:text-red-400 uppercase font-semibold flex items-center gap-1">
                          <AlertTriangle size={9} />
                          Margin{isInclusiveTax ? " (cost incl. VAT)" : ""}
                        </p>
                        <p className="text-base font-bold text-red-600 dark:text-red-400">
                          {formatCurrencyWithSymbol(marginAmount, currency_symbol)}
                        </p>
                        <p className="text-[10px] text-red-500 dark:text-red-400 mt-1">{marginPercentage.toFixed(1)}% · below cost</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {(itemDiscount.discountAmount > 0) ? (
              <div className="mt-3 p-2 bg-green-50 dark:bg-green-900/20 rounded-md border border-green-200 dark:border-green-800">
                <div className="text-xs text-green-800 dark:text-green-300 font-medium">
                  Discount Applied:
                </div>
                <div className="flex justify-between items-center mt-1">
                  <span className="text-xs text-green-700 dark:text-green-400">
                    {localDiscountPct > 0 ? `${localDiscountPct.toFixed(1)}% off` : ""}
                    {localDiscountPct > 0 ? " · " : ""}
                    {formatCurrencyWithSymbol(itemDiscount.discountAmount, currency_symbol)}
                  </span>
                  <span className="text-xs font-semibold text-green-800 dark:text-green-300">
                    Save {formatCurrencyWithSymbol(originalTotal - discountedTotal, currency_symbol)}
                  </span>
                </div>
              </div>
            ) : (
              <></>
            )}

            </div>
          </div>
        ) : (
          <></>
        )}

        <SerialBatchBundleModal
          isOpen={showBundleModal}
          onClose={() => setShowBundleModal(false)}
          onSave={handleBundleSave}
          item={{
            id: item.id,
            item_code: item.item_code,
            name: item.name,
            has_serial_no: item.has_serial_no,
            has_batch_no: item.has_batch_no,
          }}
          warehouse={warehouse}
          qty={modalQty}
          onQtyChange={handleModalQtyChange}
          availableBatches={availableBatches}
          availableSerials={availableSerials}
          entries={modalEntries}
          onEntriesChange={setModalEntries}
          isLoading={isFetchingBundleData}
          onFetchData={handleModalFetchData}
          autoFetchBatch={autoFetchBatch}
        />
      </div>

      <DescriptionDialog
        isOpen={showDescriptionDialog}
        itemName={item.name}
        initialValue={item.description || ""}
        onSave={(value) => {
          onDescriptionChange?.(item.id, value);
          setShowDescriptionDialog(false);
        }}
        onClose={() => setShowDescriptionDialog(false)}
      />

      {showProductModal && (
        <ProductDetailsModal
          item={{
            id: item.item_code || item.id,
            name: item.name,
            item_code: item.item_code,
            category: item.category,
            image: item.image,
            currency_symbol: currency_symbol,
          }}
          warehouse={warehouse}
          onClose={() => setShowProductModal(false)}
        />
      )}
    </>
  );
};
