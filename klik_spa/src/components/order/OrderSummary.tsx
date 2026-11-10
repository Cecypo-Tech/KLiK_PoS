"use client";

import { useState, useEffect, useCallback, useLayoutEffect, useRef } from "react";
import { mergesSameItem, useCartStore } from "../../stores/cartStore";
import { useProductStore } from "../../stores/productStore";
import { toast } from "react-toastify";
import { fractionInWholeUnit } from "../../utils/lineEdits";
import { ShoppingCart } from "lucide-react";
import { extractErrorFromException } from "../../utils/errorExtraction";
import { getBatches } from "../../utils/batch";
import { getSerials } from "../../utils/serial";
import { isExplicitlyNotTracked } from "../../utils/trackingFlags";
import type { CartItem, MenuItem } from "../../../types";
import type { Customer } from "../../types/customer";
import PaymentDialog from "../dialog/PaymentDialog";
import QuoteSavedDialog from "../dialog/QuoteSavedDialog";
import { createQuote } from "../../services/quotation";
import { buildOrderPayload, tillFlags } from "../../utils/heldOrderPayload";
import { checkoutPriceList } from "../../utils/priceFloor";
import SalespersonAuthModal from "../dialog/SalespersonAuthModal";
import {
  getCheckoutRequestStatus,
  validateCheckoutInvoice,
} from "../../services/salesInvoice";
import {
  getCheckoutAttemptForCart,
  getCheckoutCartFingerprint,
} from "../../utils/checkoutAttempt";
import { getOriginalDraftInvoiceId, getOriginalHeldOrderId } from "../../utils/draftInvoiceCache";
import { CustomerSearchSection } from "./CustomerSearchSection";
import CustomerLoyaltySummary from "./CustomerLoyaltySummary";
import { CartItemRow } from "./CartItemRow";
import { OrderSummaryFooter } from "./OrderSummaryFooter";
import { usePosShortcutLayer } from "../../hooks/usePosShortcutLayer";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { quotesAllowed } from "../../utils/quotesAllowed";
import { useSalespersonStore } from "../../stores/salespersonStore";
import { getEffectiveDisplayRate, getEffectiveItemRate } from "../../utils/cartPricing";
import { shouldRestorePersistedDiscount } from "../../utils/persistedDiscounts";
import { roundCurrency } from "../../utils/currencyMath";
import { formatCartWeight, getCartNetWeight } from "../../utils/cartWeight";
import { CART_ROW_GRID } from "./cartTableLayout";
import { discountForOverride } from "../../utils/rateOverrides";
import LineGrid, { type LineGridHandle } from "./LineGrid";
import DescriptionDialog from "./DescriptionDialog";
import VariantPickerModal from "../VariantPickerModal";
import { useLineGridShortcuts } from "../../hooks/useLineGridShortcuts";

interface OrderSummaryProps {
  onClearCart?: () => void;
  isMobile?: boolean;
  onPaymentCompleted?: () => void;
  /** "grid": the line-entry till (LineGrid + a side panel for the selected line). */
  layout?: "cart" | "grid";
}

export default function OrderSummary({
  onClearCart,
  isMobile = false,
  onPaymentCompleted,
  layout = "cart",
}: OrderSummaryProps) {
  const isGrid = layout === "grid";
  const {
    cartItems,
    selectedCustomer,
    setSelectedCustomer,
    updateUOM,
    refreshCartPricing,
    updateQuantity,
    removeItem,
    clearCart,
    updateItemDescription,
    expandedCartItemId,
    toggleItemExpansion,
    pendingRateOverrides,
    consumeRateOverrides,
    quoteMode,
    enterQuoteMode,
    exitQuoteMode,
    walkinDetails,
    extraFields,
    shippingRule,
    checkoutExtras,
    selectedPriceList,
    highlightItemId,
    highlightNonce,
  } = useCartStore();

  const [showPaymentDialog, setShowPaymentDialog] = useState(false);
  const [showSalespersonAuthModal, setShowSalespersonAuthModal] = useState(false);
  const [isValidatingCheckout, setIsValidatingCheckout] = useState(false);
  const [isRecoveringCheckout, setIsRecoveringCheckout] = useState(false);
  const [pendingSalespersonAction, setPendingSalespersonAction] = useState<"checkout" | "quote" | null>(null);
  const [isSavingQuote, setIsSavingQuote] = useState(false);
  const [savedQuote, setSavedQuote] = useState<{ name: string; customerName: string; phone: string } | null>(null);
  // Grid mode only.
  const gridRef = useRef<LineGridHandle>(null);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null); // same id: React bails out, no re-render
  const [descriptionFor, setDescriptionFor] = useState<string | null>(null);
  const [variantItem, setVariantItem] = useState<MenuItem | null>(null);
  // The panel follows every add or bump (scan or pick); the cashier's own focus moves select in between.
  useEffect(() => {
    if (isGrid && highlightItemId) setSelectedLineId(highlightItemId);
  }, [isGrid, highlightItemId, highlightNonce]);

  const { posDetails } = usePOSProfileStore();
  const refreshStockOnly = useProductStore((s) => s.refreshStockOnly);
  const { activeSalesperson, ensureInitialized } = useSalespersonStore();

  const [itemDiscounts, setItemDiscounts] = useState<Record<string, any>>(() => {
    const saved: Record<string, any> = {};
    cartItems.forEach(item => {
      const persistedDiscountAmount = Number((item as CartItem & { discount_amount?: number }).discount_amount) || 0;
      const persistedDiscountPercentage = Number((item as CartItem & { discount_percentage?: number }).discount_percentage) || 0;
      const persistedCustomRate = (item as CartItem & { custom_rate?: number }).custom_rate;
      const serialBatchBundle = (item as CartItem & { serial_batch_bundle?: unknown }).serial_batch_bundle;
      // A rule discount is already inside item.price; restoring it here subtracts it twice.
      const restorable = shouldRestorePersistedDiscount(item as CartItem & { original_price?: number });
      const discountAmount = restorable ? persistedDiscountAmount : 0;
      const discountPercentage = restorable ? persistedDiscountPercentage : 0;
      const selectedPriceList = (item as CartItem & { selected_price_list?: string }).selected_price_list;
      if (serialBatchBundle || item.bundle_entries) {
        saved[item.id] = {
          discountPercentage,
          discountAmount,
          customRate: persistedCustomRate,
          customRateIncludesTax: (item as CartItem & { custom_rate_includes_tax?: boolean }).custom_rate_includes_tax,
          serial_batch_bundle: serialBatchBundle,
          bundle_entries: item.bundle_entries,
          ...(selectedPriceList ? { selectedPriceList } : {}),
        };
      } else if (discountAmount > 0 || discountPercentage > 0 || persistedCustomRate !== undefined && persistedCustomRate !== null || selectedPriceList) {
        saved[item.id] = {
          discountPercentage,
          discountAmount,
          customRate: persistedCustomRate,
          customRateIncludesTax: (item as CartItem & { custom_rate_includes_tax?: boolean }).custom_rate_includes_tax,
          ...(selectedPriceList ? { selectedPriceList } : {}),
        };
      }
    });
    return saved;
  });
  const [itemBatches, setItemBatches] = useState<Record<string, any[]>>({});
  const [itemSerials, setItemSerials] = useState<Record<string, string[]>>({});

  const currency_symbol = posDetails?.currency_symbol;
  const autoFetchBatch = posDetails?.custom_autofetch_batchserial_ === 1;
  const canQuote = quotesAllowed(posDetails);
  // A till switched off for quotes drops a quote mode left over from before (it is persisted).
  useEffect(() => {
    if (!canQuote && quoteMode) exitQuoteMode();
  }, [canQuote, quoteMode, exitQuoteMode]);
  const isTaxIncludedInBasicRate =
    posDetails?.is_tax_included_in_basic_rate === 1
    || posDetails?.is_tax_included_in_basic_rate === "1"
    || posDetails?.is_tax_included_in_basic_rate === true;

  useEffect(() => {
    // A cart that survived a checkout whose response never came back. The invoice may
    // already exist on the server, so ask before letting the cashier ring it up again.
    // Only "pending" attempts are recovered: an "accepted" one was confirmed by the
    // client, and re-resolving it here would clear the cart under an open receipt.
    if (showPaymentDialog || !selectedCustomer?.id || cartItems.length === 0) {
      setIsRecoveringCheckout(false);
      return;
    }

    const cartFingerprint = getCheckoutCartFingerprint(
      selectedCustomer.id,
      cartItems as unknown as Array<Record<string, unknown>>,
    );
    const attempt = getCheckoutAttemptForCart(cartFingerprint);
    if (!attempt || attempt.status !== "pending") {
      setIsRecoveringCheckout(false);
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    const recoveryDeadline = attempt.createdAt + 30_000;

    const recoverCheckout = async () => {
      try {
        const status = await getCheckoutRequestStatus(attempt.requestId);
        if (cancelled) return;

        const invoiceName = status.invoice_name || status.invoice_id;
        if (invoiceName) {
          clearCart();
          setItemDiscounts({});
          setIsRecoveringCheckout(false);
          if (status.checkout_status === "failed") {
            toast.error(
              `Checkout recovered as ${invoiceName}, but submission failed. Retry it from Invoice History.`
            );
          } else {
            toast.success(`Previous checkout recovered as invoice ${invoiceName}.`);
          }
          onClearCart?.();
          onPaymentCompleted?.();
          return;
        }

        if (Date.now() < recoveryDeadline) {
          setIsRecoveringCheckout(true);
          timer = window.setTimeout(recoverCheckout, 2000);
        } else {
          // Give up waiting but keep the same request id, so if an invoice did land the
          // resubmission replays it rather than creating a second one.
          setIsRecoveringCheckout(false);
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to recover previous checkout:", error);
          setIsRecoveringCheckout(false);
        }
      }
    };

    setIsRecoveringCheckout(true);
    void recoverCheckout();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [cartItems, selectedCustomer?.id, showPaymentDialog, clearCart, onClearCart, onPaymentCompleted]);

  useEffect(() => {
    // When a held invoice is loaded back into cart, restore per-line discounts from persisted draft fields.
    setItemDiscounts((prev) => {
      const next: Record<string, any> = {};

      cartItems.forEach((item) => {
        const existing = prev[item.id];
        const persistedDiscountAmount = Number((item as CartItem & { discount_amount?: number }).discount_amount) || 0;
        const persistedDiscountPercentage = Number((item as CartItem & { discount_percentage?: number }).discount_percentage) || 0;
        const persistedCustomRate = (item as CartItem & { custom_rate?: number }).custom_rate;
        const serialBatchBundle = (item as CartItem & { serial_batch_bundle?: unknown }).serial_batch_bundle;
        const bundleEntries = item.bundle_entries;

        if (existing) {
          next[item.id] = {
            ...existing,
            serial_batch_bundle: existing.serial_batch_bundle ?? serialBatchBundle,
            bundle_entries: existing.bundle_entries ?? bundleEntries,
          };
          return;
        }

        // Same rule as the initialiser: never restore a discount already inside the price.
        const restorable = shouldRestorePersistedDiscount(item as CartItem & { original_price?: number });
        const discountAmount = restorable ? persistedDiscountAmount : 0;
        const discountPercentage = restorable ? persistedDiscountPercentage : 0;

        const selectedPriceList = (item as CartItem & { selected_price_list?: string }).selected_price_list;
        if (
          discountAmount > 0
          || discountPercentage > 0
          || (persistedCustomRate !== undefined && persistedCustomRate !== null)
          || serialBatchBundle
          || bundleEntries
          || selectedPriceList
        ) {
          next[item.id] = {
            discountPercentage,
            discountAmount,
            customRate: persistedCustomRate,
            customRateIncludesTax: (item as CartItem & { custom_rate_includes_tax?: boolean }).custom_rate_includes_tax,
            serial_batch_bundle: serialBatchBundle,
            bundle_entries: bundleEntries,
            ...(selectedPriceList ? { selectedPriceList } : {}),
          };
        }
      });

      return next;
    });
  }, [cartItems]);

  useEffect(() => {
    if (selectedCustomer && cartItems.length > 0) {
      // Keep saved draft pricing stable while editing a held order or invoice.
      if (getOriginalDraftInvoiceId() || getOriginalHeldOrderId()) {
        return;
      }
      refreshCartPricing();
    }
  }, [selectedCustomer?.id, cartItems.length, refreshCartPricing]);

  useEffect(() => {
    if (posDetails?.custom_sales_person_pin_required) {
      void ensureInitialized();
    }
  }, [posDetails?.custom_sales_person_pin_required, ensureInitialized]);

  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      const currentId = useCartStore.getState().expandedCartItemId;
      if (!currentId) return;

      const target = event.target as HTMLElement | null;
      if (!target) return;

      const clickedRow = target.closest("[data-cart-item-id]") as HTMLElement | null;
      const clickedItemId = clickedRow?.dataset.cartItemId;
      const activeElement = document.activeElement as HTMLElement | null;
      const activeRow = activeElement?.closest("[data-cart-item-id]") as HTMLElement | null;
      const activeItemId = activeRow?.dataset.cartItemId;
      const itemToKeepOpen =
        (clickedItemId === currentId && clickedItemId) ||
        (activeItemId === currentId && activeItemId) ||
        null;

      if (!itemToKeepOpen) {
        useCartStore.setState({ expandedCartItemId: null });
      }
    };

    document.addEventListener("click", handleDocumentClick, true);
    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
    };
  }, []);

  useEffect(() => {
    if (!autoFetchBatch) return;

    const fetchData = async () => {
      const newBatches = { ...itemBatches };
      const newSerials = { ...itemSerials };
      for (const item of cartItems) {
        const key = item.item_code || item.id;
        if (key && key !== "undefined") {
          // has_batch_no/has_serial_no are only populated on cart items added via the
          // product-tile flow. Items added by scanning a barcode never get them set, so
          // `undefined` here means "unknown", not "not tracked" — do NOT treat it as a
          // plain falsy check, or scanned batch/serial items silently lose their fetch.
          // Only skip when the backend has explicitly told us there is nothing to fetch.
          if (!newBatches[key] && !isExplicitlyNotTracked(item.has_batch_no)) {
            try {
              const batches = await getBatches(item.id);
              newBatches[key] = Array.isArray(batches) ? batches : [];
            } catch (err) {
              console.warn(`Failed to fetch batches for item ${key}:`, err);
              newBatches[key] = [];
            }
          }
          if (!newSerials[key] && !isExplicitlyNotTracked(item.has_serial_no)) {
            try {
              const serials = await getSerials(key);
              newSerials[key] = Array.isArray(serials) ? serials : [];
            } catch (err) {
              console.warn(`Failed to fetch serials for item ${key}:`, err);
              newSerials[key] = [];
            }
          }
        }
      }
      setItemBatches(newBatches);
      setItemSerials(newSerials);
    };
    if (cartItems.length) {
      fetchData().catch((err) => {
        console.warn("Failed to fetch batch/serial data for cart:", err);
      });
    }
  }, [autoFetchBatch, cartItems]);

  const getDiscountedPrice = (item: CartItem) => {
    return roundCurrency(getEffectiveItemRate(item, {
      itemDiscounts,
      isTaxIncludedInBasicRate,
    }));
  };

  const getDisplayPriceInclusive = (item: CartItem) => {
    return roundCurrency(getEffectiveDisplayRate(item, {
      itemDiscounts,
      isTaxIncludedInBasicRate,
    }));
  };

  const getOriginalDisplayPriceInclusive = (item: CartItem) => {
    return roundCurrency(getEffectiveDisplayRate(item, {
      itemDiscounts: {},
      isTaxIncludedInBasicRate,
    }));
  };

  const getLineTotalInclusive = (item: CartItem) => {
    return roundCurrency(getDisplayPriceInclusive(item) * item.quantity);
  };

  // ERPNext convention: subtotal is the net (price-list) total; tax is added on top
  // (exclusive) or already carved in (inclusive) to form the grand total shown on the
  // checkout button. This mirrors the PaymentDialog breakdown.
  const subtotal = cartItems.reduce((sum, item) => roundCurrency(sum + roundCurrency(getDiscountedPrice(item) * item.quantity)), 0);
  const grandTotal = cartItems.reduce((sum, item) => roundCurrency(sum + getLineTotalInclusive(item)), 0);
  const totalItemDiscount = cartItems.reduce((sum, item) => {
    const original = roundCurrency(getOriginalDisplayPriceInclusive(item) * item.quantity);
    const discounted = getLineTotalInclusive(item);
    return roundCurrency(sum + roundCurrency(original - discounted));
  }, 0);
  const couponDiscount = 0;
  const total = roundCurrency(Math.max(0, grandTotal - couponDiscount));
  const cartWeight = getCartNetWeight(cartItems);

  const handleUpdateQuantity = (id: string, quantity: number) => {
    // Every caller sends a real edit: the qty boxes only when typed in (qtyToSend), the
    // bundle editor only when its total differs.
    if (quantity <= 0) {
      removeItem(id);
      return;
    }
    const uom = cartItems.find((i) => i.id === id)?.uom;
    if (fractionInWholeUnit(quantity, uom, posDetails?.whole_number_uoms)) {
      toast.error(`${uom} is sold in whole units only: ${quantity} can't be used`);
    } else {
      updateQuantity(id, quantity);
    }
  };

  const handleRemoveItem = (id: string) => {
    removeItem(id);
  };

  const handleUOMChange = useCallback((itemId: string, uom: string, price: number, conversionFactor?: number) => {
    const qty = cartItems.find((i) => i.id === itemId)?.quantity ?? 0;
    if (fractionInWholeUnit(qty, uom, posDetails?.whole_number_uoms)) {
      toast.error(`${uom} is sold in whole units only: ${qty} can't be used`);
      return;
    }
    updateUOM(itemId, uom, price, conversionFactor);
  }, [updateUOM, cartItems, posDetails?.whole_number_uoms]);

  const updateItemDiscount = (itemId: string, field: string, value: number | string) => {
    setItemDiscounts(prev => ({
      ...prev,
      [itemId]: { ...(prev[itemId] || { discountPercentage: 0, discountAmount: 0 }), [field]: value }
    }));
  };

  const handleCustomRateChange = (item: CartItem, newRate?: number, includesTax?: boolean) => {
    setItemDiscounts(prev => ({
      ...prev,
      [item.id]: {
        ...(prev[item.id] || {}),
        customRate: newRate,
        customRateIncludesTax: includesTax,
        discountPercentage: 0,
        discountAmount: 0,
      }
    }));
  };

  // Fulfills a rate-override request made from outside the cart (the item
  // list's '*' shortcut, quick entry) by setting the line's discount entry the
  // way the cart's own Rate field and price-list switch do - including which
  // price list the rate came from, so the line's price chip shows it.
  const lastAppliedRateOverrideNonce = useRef(0);
  useEffect(() => {
    const fresh = pendingRateOverrides.filter((o) => o.nonce > lastAppliedRateOverrideNonce.current);
    if (fresh.length === 0) return;
    for (const override of fresh) {
      if (cartItems.some((ci) => ci.id === override.itemId)) {
        setItemDiscounts((prev) => ({ ...prev, [override.itemId]: discountForOverride(prev[override.itemId], override) }));
      }
    }
    const last = fresh[fresh.length - 1]?.nonce ?? lastAppliedRateOverrideNonce.current;
    lastAppliedRateOverrideNonce.current = last;
    consumeRateOverrides(last);
  }, [pendingRateOverrides, cartItems, consumeRateOverrides]);

  const handleBundleUpdate = (itemId: string, bundleId: string, entries: any[]) => {
    updateItemDiscount(itemId, "serial_batch_bundle", bundleId);
    updateItemDiscount(itemId, "bundle_entries", JSON.stringify(entries));
  };

  const handleDuplicateItem = (item: CartItem) => {
    const newItem = {
      ...item,
      id: `${item.item_code || item.id}-${Date.now()}`,
      item_code: item.item_code || item.id,
      quantity: 1,
    };
    useCartStore.getState().addToCart(newItem, { merge: false });
  };

  const handleCustomerSelect = (customer: Customer) => {
    setSelectedCustomer(customer);
  };

  const handleCustomerClear = () => {
    setSelectedCustomer(null);
  };

  const validateCustomer = () => {
    if (!selectedCustomer) {
      toast.error("Kindly choose customer");
      return false;
    }
    return true;
  };

  // The cart lines as checkout gets them, with their computed prices.
  const checkoutLines = () => cartItems.map((item) => ({
    ...item,
    discountedPriceExcl: getDiscountedPrice(item),
    discountedPriceIncl: getDisplayPriceInclusive(item),
    discountedPrice: getDisplayPriceInclusive(item),
    itemDiscount: itemDiscounts[item.id] || {},
    originalPrice: roundCurrency(item.price),
    finalAmount: getLineTotalInclusive(item),
  }));

  // Straight to create_quote: checkout's server stock check would refuse a quote over stock.
  const saveQuote = async () => {
    if (!validateCustomer() || !selectedCustomer || isSavingQuote) return;
    setIsSavingQuote(true);
    try {
      const payload = buildOrderPayload({
        cartItems: checkoutLines(),
        itemDiscounts,
        effectiveRate: getDiscountedPrice,
        customer: selectedCustomer,
        totals: {
          subtotal,
          grandTotal: total,
          taxAmount: roundCurrency(Math.max(0, total - subtotal)),
          isInclusive: isTaxIncludedInBasicRate,
          couponDiscount,
        },
        appliedCoupons: [],
        businessType: posDetails?.business_type,
        salesperson: activeSalesperson?.name || null,
        sellingPriceList: checkoutPriceList(posDetails, selectedPriceList),
        // Delivery, order discount, tax template and remarks as checkout last left them.
        extras: {
          walkin: walkinDetails,
          extraFields,
          shippingRule,
          extras: checkoutExtras,
          flags: tillFlags(posDetails as Record<string, unknown>),
        },
        loyalty: null,
      });
      const result = await createQuote(payload);
      if (!result.success || !result.quote_name) {
        toast.error(result.message || "Failed to save the quote");
        return;
      }
      const customerName = walkinDetails.name?.trim() || selectedCustomer.name;
      const phone = walkinDetails.phone?.trim() || selectedCustomer.phone || "";
      clearCart();
      setItemDiscounts({});
      exitQuoteMode();
      setSavedQuote({ name: result.quote_name, customerName, phone });
    } catch (e) {
      toast.error(extractErrorFromException(e, "Failed to save the quote"));
    } finally {
      setIsSavingQuote(false);
    }
  };

  const startCheckoutFlow = async () => {
    if (!validateCustomer() || isValidatingCheckout) return;
    setIsValidatingCheckout(true);
    try {
      const payload = {
        customer: { id: selectedCustomer?.id },
        items: cartItems.map(item => ({
          id: item.item_code || item.id,
          quantity: item.quantity,
          los_qty: item.los_qty ?? 0,
          price: getDiscountedPrice(item),
          uom: item.uom || "Nos",
          serial_batch_bundle: item.bundle_entries,
        })),
        itemDiscounts,
        businessType: posDetails?.business_type,
      };
      const result = await validateCheckoutInvoice(payload);
      if (!useCartStore.getState().quoteMode) await useCartStore.getState().applyCheckoutLosAdjustments(result?.los_adjustments ?? []);
      setShowPaymentDialog(true);
    } catch (error) {
      toast.error(extractErrorFromException(error, "Checkout validation failed"));
    } finally {
      setIsValidatingCheckout(false);
    }
  };

  const requireSalespersonAndRun = async (action: "checkout" | "quote") => {
    const requiresSalespersonPin = !!posDetails?.custom_sales_person_pin_required;
    if (!requiresSalespersonPin || activeSalesperson) {
      await (action === "quote" ? saveQuote() : startCheckoutFlow());
      return;
    }

    setPendingSalespersonAction(action);
    setShowSalespersonAuthModal(true);
  };

  const handleCheckoutClick = async () => {
    if (isRecoveringCheckout) {
      toast.info("Checking whether the previous checkout already created an invoice.");
      return;
    }
    await requireSalespersonAndRun(quoteMode ? "quote" : "checkout");
  };

  const handleClearCart = () => {
    if (cartItems.length === 0) return;
    clearCart();
    setItemDiscounts({});
    onClearCart?.();
  };

  const handleSalespersonAuthenticated = () => {
    const nextAction = pendingSalespersonAction;
    setPendingSalespersonAction(null);
    setShowSalespersonAuthModal(false);

    if (nextAction === "checkout") {
      void startCheckoutFlow();
    } else if (nextAction === "quote") {
      void saveQuote();
    }
  };

  // F10 and Shift+F10 both open checkout from the cart (save the quote, when quoting); Hold
  // lives in checkout, whose own layer then takes Shift+F10 (hold) and F10 (submit). Off while
  // this summary's payment dialog is open: a cart refilled behind it would otherwise push this
  // layer on top.
  const openCheckoutFromShortcut = () => {
    if (isValidatingCheckout || isSavingQuote) return;
    void handleCheckoutClick();
  };
  // A grid cell commits on blur: blur it, then check out on the next tick, from the render that
  // has the edit (the ref holds that render's handler).
  const checkoutShortcutRef = useRef(openCheckoutFromShortcut);
  useLayoutEffect(() => {
    checkoutShortcutRef.current = openCheckoutFromShortcut;
  });
  const checkoutFromShortcut = () => {
    if (!isGrid) return openCheckoutFromShortcut();
    (document.activeElement as HTMLElement | null)?.blur?.();
    setTimeout(() => checkoutShortcutRef.current(), 0);
  };
  usePosShortcutLayer(
    {
      f10: checkoutFromShortcut,
      shiftF10: checkoutFromShortcut,
    },
    cartItems.length > 0 && !showPaymentDialog && !savedQuote,
  );

  const handleCompletePayment = async (paymentData: any) => {
  };

  const handleClosePaymentDialog = async (paymentCompleted?: boolean) => {
    setShowPaymentDialog(false);
    if (paymentCompleted) {
      handleClearCart();
      onPaymentCompleted?.();
    }

    try {
      await refreshStockOnly();
      const cartItemCodes = cartItems.map((item) => item.item_code || item.id);
      if (cartItemCodes.length > 0) {
        // await updateBatchQuantitiesForItems(cartItemCodes);
      }
    } catch (error: any) {
      console.error("OrderSummary: Failed to refresh stock:", error);
      toast.error(`Failed to update stock: ${error.message || "Unknown error"}`);
    }
  };

  const focusEntry = () => gridRef.current?.focusEntry();
  useLineGridShortcuts(
    {
      focusEntry,
      focusPanel: () => document.getElementById("pos-line-panel")?.focus(),
      // One help panel: the top bar's (MenuGrid, header-only in grid mode).
      toggleHelp: () => document.getElementById("pos-shortcuts-btn")?.click(),
    },
    // Off under a modal: F3/F8 would move focus behind it.
    isGrid && !showPaymentDialog && !descriptionFor && !variantItem && !savedQuote && !showSalespersonAuthModal,
  );

  const pickGridItem = async (item: MenuItem): Promise<string | null> => {
    if (item.is_variant_template || item.has_variants) {
      setVariantItem(item);
      return null;
    }
    return useCartStore.getState().addToCartQueued({ ...item, item_code: item.id }, { merge: mergesSameItem() });
  };

  const customerHeader = (
    <div className={!isMobile ? "px-6 py-4 border-b border-gray-100 dark:border-gray-700" : ""}>
      <CustomerSearchSection
        selectedCustomer={selectedCustomer}
        onCustomerSelect={handleCustomerSelect}
        onCustomerClear={handleCustomerClear}
        isMobile={isMobile}
      />
      <CustomerLoyaltySummary
        customer={selectedCustomer}
        currencySymbol={currency_symbol}
      />
    </div>
  );

  const quoteBanner = quoteMode && (
    <div
      role="status"
      className="flex items-center justify-between gap-3 px-4 py-2 bg-amber-100 dark:bg-amber-900/40 border-b border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-200 text-sm"
    >
      <span className="font-semibold">QUOTE MODE — not a sale; stock is not limited</span>
      <button
        id="pos-cancel-quote-btn"
        onClick={exitQuoteMode}
        className="shrink-0 rounded-lg border border-amber-500 px-2 py-1 text-xs font-medium hover:bg-amber-200 dark:hover:bg-amber-800/40"
      >
        Cancel quote
      </button>
    </div>
  );

  const quoteButton = !quoteMode && canQuote && (
    <button
      id="pos-quote-btn"
      onClick={enterQuoteMode}
      className="mt-4 px-3 py-2 border border-amber-500 text-amber-700 dark:text-amber-400 rounded-xl font-medium hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors text-sm"
    >
      Quote
    </button>
  );

  const cartRow = (item: CartItem, isExpanded: boolean, onToggleExpand: () => void) => (
    <CartItemRow
      key={item.id}
      item={item}
      itemId={item.id}
      isExpanded={isExpanded}
      onToggleExpand={onToggleExpand}
      itemDiscount={itemDiscounts[item.id] || {
        discountPercentage: 0,
        discountAmount: 0,
        batchNumber: "",
        serialNumber: "",
        availableQuantity: 150,
      }}
      onUpdateQuantity={handleUpdateQuantity}
      onRemoveItem={handleRemoveItem}
      onUOMChange={handleUOMChange}
      onDiscountChange={updateItemDiscount}
      onCustomRateChange={handleCustomRateChange}
      onDuplicateItem={handleDuplicateItem}
      onBundleUpdate={handleBundleUpdate}
      onDescriptionChange={updateItemDescription}
      selectedCustomer={selectedCustomer}
      posDetails={posDetails}
      itemBatches={itemBatches[item.item_code || item.id] || []}
      itemSerials={itemSerials[item.item_code || item.id] || []}
      currency_symbol={currency_symbol}
      isMobile={isMobile}
      autoFetchBatch={autoFetchBatch}
    />
  );

  const footer = cartItems.length > 0 && (
    <OrderSummaryFooter
      subtotal={subtotal}
      total={total}
      totalItemDiscount={totalItemDiscount}
      couponDiscount={couponDiscount}
      onCheckout={handleCheckoutClick}
      onClearCart={handleClearCart}
      isValidating={isValidatingCheckout || isRecoveringCheckout || isSavingQuote}
      isMobile={isMobile}
      currency_symbol={currency_symbol}
      taxExclusive={!isTaxIncludedInBasicRate}
      netWeightLabel={cartWeight.total > 0 ? formatCartWeight(cartWeight) : ""}
      quoteMode={quoteMode}
      onQuote={canQuote ? enterQuoteMode : undefined}
    />
  );

  const dialogs = (
    <>
      {showPaymentDialog && (
        <PaymentDialog
          isOpen={showPaymentDialog}
          backLabel="Back to cart"
          showAdditionalInfo
          onClose={handleClosePaymentDialog}
          cartItems={checkoutLines()}
          appliedCoupons={[]}
          selectedCustomer={selectedCustomer}
          onCompletePayment={handleCompletePayment}
          onHoldOrder={() => setShowPaymentDialog(false)}
          isMobile={isMobile}
          itemDiscounts={itemDiscounts}
          totalItemDiscount={totalItemDiscount}
        />
      )}

      {savedQuote && (
        <QuoteSavedDialog
          quoteName={savedQuote.name}
          customerName={savedQuote.customerName}
          phone={savedQuote.phone}
          posDetails={posDetails}
          onDone={() => setSavedQuote(null)}
        />
      )}

      <SalespersonAuthModal
        isOpen={showSalespersonAuthModal}
        onClose={() => {
          setShowSalespersonAuthModal(false);
          setPendingSalespersonAction(null);
        }}
        onAuthenticated={handleSalespersonAuthenticated}
        allowDismiss
        title="Start transaction"
        description="Verify the salesperson before checkout or holding this order."
      />
    </>
  );

  if (isGrid) {
    const lineIds = (id: string | null) => (id && cartItems.some((i) => i.id === id) ? id : null);
    // Nothing picked (or it was removed): follow the line the cart last added to or bumped.
    const selectedId = lineIds(selectedLineId) ?? lineIds(highlightItemId);
    const selected = cartItems.find((i) => i.id === selectedId);
    const descriptionLine = cartItems.find((i) => i.id === descriptionFor);
    return (
      <div className="h-full flex bg-white dark:bg-gray-800">
        {/* The payment page sits over the cart: nothing under it may take focus or a stray key. */}
        <div className="contents" inert={showPaymentDialog}>
        <div className="flex-1 min-w-0 flex flex-col">
          {quoteBanner}
          <div className="flex-1 overflow-y-auto cart-scroll">
            <LineGrid
              ref={gridRef}
              items={cartItems}
              itemDiscounts={itemDiscounts}
              selectedId={selectedId}
              onSelect={setSelectedLineId}
              onUpdateQuantity={handleUpdateQuantity}
              onCustomRateChange={handleCustomRateChange}
              onDiscountChange={updateItemDiscount}
              onRemoveItem={handleRemoveItem}
              onUOMChange={handleUOMChange}
              customerId={selectedCustomer?.id}
              onOpenDescription={setDescriptionFor}
              onPickItem={pickGridItem}
              currencySymbol={currency_symbol || ""}
              posDetails={posDetails}
            />
          </div>
        </div>
        <div className="w-[380px] shrink-0 flex flex-col border-l border-gray-200 dark:border-gray-700 shadow-lg">
          {customerHeader}
          <div
            id="pos-line-panel"
            tabIndex={-1}
            className="flex-1 overflow-y-auto cart-scroll outline-none focus-visible:ring-2 focus-visible:ring-beveren-400/50"
            onKeyDown={(e) => {
              // Esc goes back to the grid, unless it belongs to a modal/popup opened from the panel.
              if (e.key !== "Escape" || (e.target as HTMLElement).closest(".fixed, [role='dialog']")) return;
              e.preventDefault();
              focusEntry();
            }}
          >
            {selected ? (
              cartRow(selected, true, () => {})
            ) : (
              <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                {cartItems.length ? "Select a line" : "Scan or type an item to start"}
                {cartItems.length === 0 && <div>{quoteButton}</div>}
              </div>
            )}
          </div>
          {footer}
        </div>
        </div>

        {dialogs}
        <DescriptionDialog
          isOpen={!!descriptionLine}
          itemName={descriptionLine?.name || ""}
          initialValue={descriptionLine?.description || ""}
          onSave={(value) => {
            if (descriptionLine) updateItemDescription(descriptionLine.id, value);
            setDescriptionFor(null);
            focusEntry();
          }}
          onClose={() => setDescriptionFor(null)}
        />
        {variantItem && (
          <VariantPickerModal
            item={variantItem}
            customerId={selectedCustomer?.id}
            onClose={() => { setVariantItem(null); focusEntry(); }}
            onSelectVariant={async (variant) => { await pickGridItem(variant); }}
          />
        )}
      </div>
    );
  }

  return (
    <div
      className={`${
        isMobile ? "h-full flex flex-col" : "h-full flex flex-col"
      } bg-white dark:bg-gray-800 ${
        !isMobile ? "border-l" : ""
      } border-gray-200 dark:border-gray-700`}
    >
      <div className="contents" inert={showPaymentDialog}>
      {customerHeader}

      {quoteBanner}

      <div
        className={`${
          isMobile
            ? "flex-1 overflow-y-auto custom-scrollbar"
            : "flex-1 overflow-y-auto cart-scroll"
        }`}
      >
        {/* A table like the product list: one header, rows split by a rule, no cards. */}
        {cartItems.length > 0 && (
          <div
            className={`${CART_ROW_GRID} sticky top-0 z-10 px-3 py-1.5 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400`}
          >
            <span>Item</span>
            <span className="text-center">Qty</span>
            <span className="text-right">Rate</span>
            <span className="text-right">Total</span>
          </div>
        )}
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {cartItems.length === 0 ? (
            <div className="text-center py-8">
              <ShoppingCart className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Your cart is empty
              </h3>
              <p className="text-gray-500 dark:text-gray-400">
                Add some items to get started!
              </p>
              {quoteButton}
            </div>
          ) : (
            cartItems.map((item) =>
              cartRow(item, expandedCartItemId === item.id, () => toggleItemExpansion(item.id))
            )
          )}
        </div>
      </div>

      {footer}
      </div>

      {dialogs}
    </div>
  );
}
