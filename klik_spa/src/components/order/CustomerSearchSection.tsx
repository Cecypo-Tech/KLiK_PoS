"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { 
  Search, 
  ChevronDown, 
  X, 
  Loader2, 
  Check,
  User,
  UserPlus,
  Mail,
  Phone,
  Contact,
  Tag,
  Warehouse,
} from "lucide-react";
import type { Customer } from "../../types/customer";
import { transformCustomerInfo } from "../../utils/transformCustomerInfo";
import { useCustomers } from "../../hooks/useCustomers";
import { useCustomerPermission } from "../../hooks/useCustomerPermission";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { useProductStore } from "../../stores/productStore";
import { useCartStore } from "../../stores/cartStore";
import { useExtraFields } from "../../hooks/useExtraFields";
import countryList from "react-select-country-list";
import { parsePhoneNumber } from "react-phone-number-input";
import { customerBadge, customerRowDetails } from "../../utils/customerRow";
import AddCustomerModal from "../customer/AddCustomerModal";
import { CustomerIcon } from "./customerMarks";
import OverdueWarningModal from "../customer/OverdueWarningModal";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  // @ts-expect-error ignore
} from "@/components/ui/alert-dialog";

const PICKER =
  "w-full truncate h-9 pl-8 pr-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-beveren-500 focus:border-transparent disabled:opacity-60";
const FOOTER_BTN =
  "flex-1 flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium text-beveren-700 dark:text-beveren-300 hover:bg-beveren-50 dark:hover:bg-beveren-900/30 transition-colors";
const PICKER_ICON = "pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400";

interface CustomerSearchSectionProps {
  selectedCustomer: Customer | null;
  onCustomerSelect: (customer: Customer) => void;
  onCustomerClear: () => void;
  isMobile?: boolean;
  /** "bar": one line in the grid till's top bar, pickers beside it. Default: the cart panel's card. */
  variant?: "panel" | "bar";
}

/** After a customer pick the cashier scans next: the grid's entry row, or the cart's search box. */
const focusItemEntry = () =>
  document.querySelector<HTMLElement>("[data-entry-row] input, #pos-search-input")?.focus();

interface SellingPriceList {
  name: string;
  currency?: string;
}

export const CustomerSearchSection = ({
  selectedCustomer,
  onCustomerSelect,
  onCustomerClear,
  isMobile = false,
  variant = "panel",
}: CustomerSearchSectionProps) => {
  const bar = variant === "bar";
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<"top" | "bottom">("bottom");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [showAddCustomerModal, setShowAddCustomerModal] = useState(false);
  const [prefilledCustomerName, setPrefilledCustomerName] = useState("");
  const [prefilledData, setPrefilledData] = useState<{
    name?: string;
    email?: string;
    phone?: string;
  }>({});
  const [userRemovedDefaultCustomer, setUserRemovedDefaultCustomer] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const buttonRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isSelectingRef = useRef(false);
  const shouldPreventSearchRef = useRef(false);

  const { customers, isLoading: isLoadingCustomers, refetch: refetchCustomers } = useCustomers(search);
  const { posDetails, warehouse: selectedWarehouse, setWarehouse } = usePOSProfileStore();
  const { checkCustomerPermission } = useCustomerPermission();
  const fetchProducts = useProductStore((s) => s.fetchProducts);
  const setProductCustomer = useProductStore((s) => s.setSelectedCustomer);
  const selectedPriceList = useCartStore((state) => state.selectedPriceList);
  const setSelectedPriceList = useCartStore((state) => state.setSelectedPriceList);
  const walkinDetails = useCartStore((state) => state.walkinDetails);
  const extraFields = useCartStore((state) => state.extraFields);
  const { fields: extraFieldDefs } = useExtraFields();
  const setAdditionalInfoOpen = useCartStore((state) => state.setAdditionalInfoOpen);
  const [overdueData, setOverdueData] = useState<{
    invoices: Array<{
      name: string; due_date: string; grand_total: number;
      outstanding_amount: number; currency: string; customer_name: string;
    }>;
    customerName: string;
  } | null>(null);
  const [priceLists, setPriceLists] = useState<SellingPriceList[]>([]);
  const [isLoadingPriceLists, setIsLoadingPriceLists] = useState(false);
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [isLoadingWarehouses, setIsLoadingWarehouses] = useState(false);

  const canCreateCustomer = posDetails?.custom_allow_to_create_and_edit_customers === 1;
  const allowPriceListSwitching = !!posDetails?.allow_price_list_switching;
  const allowWarehouseChange = !!posDetails?.allow_warehouse_change;
  const defaultPriceList = selectedCustomer?.sellingPriceList || posDetails?.selling_price_list || "";
  const activePriceList = selectedPriceList || defaultPriceList;
  const activeWarehouse = selectedWarehouse || posDetails?.warehouse || "";

  useEffect(() => {
    let cancelled = false;
    const fetchPriceLists = async () => {
      setIsLoadingPriceLists(true);
      try {
        const response = await fetch("/api/method/klik_pos.api.item.pricing.get_selling_price_lists", {
          credentials: "include",
        });
        const data = await response.json();
        if (!cancelled) {
          setPriceLists(data?.message?.price_lists || []);
        }
      } catch (error) {
        console.error("Failed to fetch selling price lists:", error);
      } finally {
        if (!cancelled) setIsLoadingPriceLists(false);
      }
    };

    fetchPriceLists();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!allowWarehouseChange) return;
    let cancelled = false;
    const fetchWarehouses = async () => {
      setIsLoadingWarehouses(true);
      try {
        const response = await fetch("/api/method/klik_pos.api.pos_profile.get_warehouses", {
          credentials: "include",
        });
        const data = await response.json();
        if (!cancelled) {
          setWarehouses(data?.message?.warehouses || []);
        }
      } catch (error) {
        console.error("Failed to fetch warehouses:", error);
      } finally {
        if (!cancelled) setIsLoadingWarehouses(false);
      }
    };
    fetchWarehouses();
    return () => {
      cancelled = true;
    };
  }, [allowWarehouseChange]);

  const cartCount = useCartStore((state) => state.cartItems.length);
  const [warehouseBlocked, setWarehouseBlocked] = useState(false);

  const handleWarehouseChange = async (value: string) => {
    // Every cart line was added under the picked warehouse; switching would sell them from another.
    if (cartCount > 0) {
      setWarehouseBlocked(true);
      return;
    }
    setWarehouse(value || null);
    await fetchProducts(true);
  };

  const fetchCustomerInfo = async (customerName: string): Promise<Customer | null> => {
    try {
      const response = await fetch(`/api/method/klik_pos.api.customer.get_customer_info?customer_name=${encodeURIComponent(customerName)}`);
      const resData = await response.json();

      if (!resData.message || resData.message.success === false) {
        throw new Error(resData.message?.error || "Failed to fetch customer info");
      }

      const customer = resData.message;
      
      const transformedCustomer: Customer = transformCustomerInfo(customer, (typeof posDetails?.company === "object" ? posDetails?.company?.country : undefined) || "");
      
      return transformedCustomer;
    } catch (error) {
      console.error("Error fetching customer info:", error);
      return null;
    }
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
          setIsOpen(false);
          setSearch("");
          setHighlightedIndex(-1);
        }
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "F4") return;
      const el = document.activeElement as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;
      if (!selectedCustomer) return;
      e.preventDefault();
      setAdditionalInfoOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedCustomer, setAdditionalInfoOpen]);

  useEffect(() => {
    if (isOpen && inputRef.current && !isSelectingRef.current) {
      inputRef.current.focus();
      calculateDropdownPosition();
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && search.length >= 2 && !isSelectingRef.current && !shouldPreventSearchRef.current) {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }

      setIsLoading(true);
      searchTimeoutRef.current = setTimeout(async () => {
        setIsLoading(false);
      }, 300);
    }
  }, [search]);

  useEffect(() => {
    if (posDetails?.default_customer && !selectedCustomer && !userRemovedDefaultCustomer) {
      const defaultCustomer = posDetails.default_customer as any;
      checkCustomerPermission(defaultCustomer.id).then(async (result) => {
        if (result.success && result.has_permission) {
          const fullCustomer = await fetchCustomerInfo(defaultCustomer.name);
          if (fullCustomer) {
            await handleSelect(fullCustomer);
          }
        }
      });
    }
  }, [posDetails, selectedCustomer, userRemovedDefaultCustomer, checkCustomerPermission]);

  const calculateDropdownPosition = () => {
    if (!buttonRef.current) return;

    const rect = buttonRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const spaceBelow = viewportHeight - rect.bottom;
    const spaceAbove = rect.top;

    setDropdownPosition(spaceBelow < 360 && spaceAbove > spaceBelow ? "top" : "bottom");
  };

  const handleSelect = async (customer: Customer) => {
    // Immediately close dropdown and prevent any further search
    setIsOpen(false);
    setSearch("");
    setHighlightedIndex(-1);
    
    isSelectingRef.current = true;
    shouldPreventSearchRef.current = true;
    
    setIsLoading(true);
    // Every step after the click is a round trip to the server; on a till far from it each one
    // shows. The overdue check needs only the customer's id, so it goes alongside the details,
    // and the product list reloads in the background behind its own loader.
    void checkOverdue(customer);
    try {
      const resolved = (await fetchCustomerInfo(customer.name)) ?? customer;
      onCustomerSelect(resolved);
      setProductCustomer(resolved);
      if (!selectedPriceList && resolved.sellingPriceList) {
        await setSelectedPriceList(resolved.sellingPriceList);
      }
    } catch (error) {
      console.error("Error fetching customer info:", error);
      onCustomerSelect(customer);
      setProductCustomer(customer);
    } finally {
      setIsLoading(false);
      setUserRemovedDefaultCustomer(false);
      if (!isMobile) focusItemEntry(); // a phone would pop its keyboard
      setTimeout(() => {
        isSelectingRef.current = false;
        shouldPreventSearchRef.current = false;
      }, 300);
    }
    void fetchProducts(true);
  };

  const checkOverdue = async (customer: Customer) => {
    if (!posDetails?.custom_show_overdue_warning || customer.isWalkin === 1 || (customer as { is_walkin?: number }).is_walkin === 1) return;
    const company = typeof posDetails.company === "string" ? posDetails.company : (posDetails.company as any)?.name ?? "";
    try {
      const params = new URLSearchParams({ customer: customer.id, company });
      const res = await fetch(`/api/method/klik_pos.api.customer.get_customer_overdue_invoices?${params.toString()}`);
      const json = await res.json();
      const message = json?.message;
      // Same call, so the credit card's balance and this popup never disagree.
      if (message && typeof message.total_outstanding === "number") {
        const overdue = (message.invoices || []).reduce((sum: number, inv: { outstanding_amount?: number }) => sum + Number(inv.outstanding_amount || 0), 0);
        useCartStore.getState().setCustomerBalance({ customer: customer.id, outstanding: message.total_outstanding, overdue });
      }
      if (message?.has_overdue) {
        setOverdueData({
          invoices: json.message.invoices,
          customerName: json.message.customer_name || customer.name,
        });
      }
    } catch (e) {
      console.error("Overdue check failed:", e);
    }
  };

  const handlePriceListChange = async (value: string) => {
    // setSelectedPriceList re-prices the cart itself.
    await setSelectedPriceList(value || null);
    await fetchProducts(true);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    isSelectingRef.current = true;
    shouldPreventSearchRef.current = true;
    setUserRemovedDefaultCustomer(true);
    onCustomerClear();
    setProductCustomer(null);
    setSearch("");
    setIsOpen(true);
    setHighlightedIndex(-1);
    inputRef.current?.focus();
    setTimeout(() => {
      isSelectingRef.current = false;
      shouldPreventSearchRef.current = false;
    }, 300);
  };

  const handleOpenDropdown = () => {
    if (!isSelectingRef.current && !shouldPreventSearchRef.current) {
      setIsOpen(!isOpen);
      if (!isOpen) {
        setSearch("");
        setHighlightedIndex(-1);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < customers.length - 1 ? prev + 1 : prev
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        if (highlightedIndex === 0) {
          setIsOpen(false);
          setHighlightedIndex(-1);
        } else {
          setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : -1));
        }
        break;
      case "Enter":
        e.preventDefault();
        if (highlightedIndex >= 0 && customers[highlightedIndex]) {
          handleSelect(customers[highlightedIndex]);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setSearch("");
        setHighlightedIndex(-1);
        focusItemEntry();
        break;
    }
  };

  const handleAddCustomerClick = () => {
    setIsOpen(false);
    const trimmedValue = search.trim();
    let prefilledData = {};

    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedValue)) {
      prefilledData = { email: trimmedValue };
    } else if (
      /^[\d\s+()-]+$/.test(trimmedValue) &&
      trimmedValue.replace(/[\s+()-]/g, "").length >= 7
    ) {
      const companyCountryCode = (
        countryList().getData() as { value: string; label: string }[]
      ).find((c) => c.label === (posDetails?.company?.country || ""))?.value || "";

      let formattedPhone = trimmedValue;
      try {
        const parsed = parsePhoneNumber(trimmedValue, companyCountryCode as any);
        if (parsed) {
          formattedPhone = parsed.format("E.164");
        }
      } catch {
      }
      prefilledData = { phone: formattedPhone };
    } else {
      prefilledData = { name: trimmedValue };
    }

    setPrefilledData(prefilledData);
    setPrefilledCustomerName(trimmedValue);
    setShowAddCustomerModal(true);
  };

  const handleSaveCustomer = async (newCustomer: Partial<Customer> & { customer_name?: string }) => {
    if (newCustomer && newCustomer.customer_name) {
      try {
        const response = await fetch(
          `/api/method/klik_pos.api.customer.get_customer_info?customer_name=${encodeURIComponent(newCustomer.customer_name)}`
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const resData = await response.json();
        if (resData.message) {
          const fullCustomer = await fetchCustomerInfo(newCustomer.customer_name);
          if (fullCustomer) {
            await handleSelect(fullCustomer);
          }
          refetchCustomers?.();
        }
      } catch (error) {
        console.error("Error fetching customer details:", error);
        const customerToSelect: Customer = {
          id: newCustomer.customer_name || "",
          name: newCustomer.customer_name || "",
          customer_name: newCustomer.customer_name || "",
          email: newCustomer.email || "",
          phone: newCustomer.phone || "",
          type: "individual",
          address: { street: "", city: "", state: "", zipCode: "", country: posDetails?.company?.country || "" },
          loyaltyPoints: 0,
          totalSpent: 0,
          totalOrders: 0,
          preferredPaymentMethod: "Cash",
          tags: [],
          status: "active",
          is_walkin: 0,
          taxId: newCustomer.taxId,
          createdAt: new Date().toISOString(),
        };
        await handleSelect(customerToSelect);
      }
    }
    setShowAddCustomerModal(false);
    setPrefilledCustomerName("");
    setPrefilledData({});
  };

  const isLoadingState = isLoading || isLoadingCustomers;

  const dropdown = isOpen ? (
    <div
      ref={dropdownRef}
      style={{
        position: "fixed",
        top: dropdownPosition === "bottom" && buttonRef.current
          ? buttonRef.current.getBoundingClientRect().bottom + 8
          : undefined,
        bottom: dropdownPosition === "top" && buttonRef.current
          ? window.innerHeight - buttonRef.current.getBoundingClientRect().top + 8
          : undefined,
        left: buttonRef.current ? buttonRef.current.getBoundingClientRect().left : 0,
        // Wider than the box when there is room: a row's phone | email | PIN | town is one line.
        width: buttonRef.current
          ? Math.min(
              Math.max(buttonRef.current.getBoundingClientRect().width, 440),
              window.innerWidth - buttonRef.current.getBoundingClientRect().left - 8,
            )
          : 360,
        zIndex: 999999,
      }}
      className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-2xl overflow-hidden animate-in fade-in duration-200"
    >
      <div className="p-3 border-b border-gray-100 dark:border-gray-800">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            className="w-full pl-10 pr-10 py-2.5 text-sm bg-gray-50 dark:bg-gray-800 rounded-lg outline-none focus:ring-2 focus:ring-blue-500 transition-all"
            placeholder="Search by name, phone, or email..."
            autoFocus
          />
          {isLoadingState && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
          )}
        </div>
      </div>

      <div className="max-h-96 overflow-y-auto">
        {isLoadingState ? (
          <div className="p-12 text-center">
            <Loader2 className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-3" />
            <div className="text-sm text-gray-400">Searching customers...</div>
          </div>
        ) : customers.length > 0 ? (
          customers.map((customer, idx) => {
            const badge = customerBadge(customer);
            const isSelected = selectedCustomer?.id === customer.id;
            
            return (
              <div
                key={customer.id}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleSelect(customer);
                }}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className={`
                  px-4 py-3 cursor-pointer transition-all
                  hover:bg-gray-50 dark:hover:bg-gray-800
                  ${highlightedIndex === idx ? "bg-gray-50 dark:bg-gray-800" : ""}
                  ${isSelected ? "bg-blue-50 dark:bg-blue-900/20" : ""}
                  border-b border-gray-100 dark:border-gray-800 last:border-b-0
                `}
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5"><CustomerIcon customer={customer} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-white text-sm truncate">
                        {customer.name}
                      </span>
                      {badge && (
                        <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${badge.color}`}>
                          {badge.label}
                        </span>
                      )}
                      {isSelected && (
                        <Check className="w-3.5 h-3.5 shrink-0 ml-auto text-blue-600 dark:text-blue-400" />
                      )}
                    </div>
                    {customerRowDetails(customer) && (
                      <div className="mt-1 truncate text-xs tracking-tight text-gray-500 dark:text-gray-400" title={customerRowDetails(customer)}>
                        {customerRowDetails(customer)}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="p-8 text-center">
            <div className="text-sm text-gray-400">No customers found</div>
            {canCreateCustomer && (
              <button
                onClick={handleAddCustomerClick}
                className="mt-3 text-sm text-blue-600 dark:text-blue-400 hover:underline"
              >
                Create "{search}" as new customer?
              </button>
            )}
          </div>
        )}
      </div>
      {(canCreateCustomer || selectedCustomer) && (
        <div className="flex border-t border-gray-100 dark:border-gray-800">
          {canCreateCustomer && (
            <button type="button" onClick={handleAddCustomerClick} className={FOOTER_BTN}>
              <UserPlus className="w-4 h-4" aria-hidden /> New customer
            </button>
          )}
          {selectedCustomer && (
            <button
              type="button"
              onClick={() => { setIsOpen(false); setAdditionalInfoOpen(true); }}
              className={FOOTER_BTN}
            >
              <Contact className="w-4 h-4" aria-hidden /> Additional info
              <kbd className="text-[10px] font-sans text-gray-400">F4</kbd>
            </button>
          )}
        </div>
      )}
    </div>
  ) : null;

  const walkin = selectedCustomer?.isWalkin === 1;
  const phone = walkin ? walkinDetails.phone : selectedCustomer?.phone !== "N/A" ? selectedCustomer?.phone : "";
  const badge = selectedCustomer ? customerBadge(selectedCustomer) : null;
  const badgePill = badge && (
    <span className={`shrink-0 text-[11px] leading-none px-1.5 py-0.5 rounded ${badge.color}`}>{badge.label}</span>
  );
  const fixedWarehouse = !allowWarehouseChange && activeWarehouse;

  const card = selectedCustomer ? (
    bar ? (
      <div className="flex-1 min-w-0 flex items-center gap-2" title={[selectedCustomer.name, phone].filter(Boolean).join(" · ")}>
        <CustomerIcon customer={selectedCustomer} size={16} />
        <span className="truncate font-medium text-gray-900 dark:text-white text-sm">{selectedCustomer.name}</span>
        {/* Tight bar: the name wins over the badge. */}
        <span className="hidden xl:contents">{badgePill}</span>
        {phone && <span className="hidden xl:inline shrink-0 text-xs text-gray-500 dark:text-gray-400">{phone}</span>}
      </div>
    ) : (
      <div className="flex-1 min-w-0 flex items-center gap-3 py-2">
        <CustomerIcon customer={selectedCustomer} />
        <div className="flex-1 min-w-0">
        <div className="font-medium text-gray-900 dark:text-white text-sm leading-tight line-clamp-2 break-words" title={selectedCustomer.name}>
          {selectedCustomer.name}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1">
          {badgePill}
          {phone && (
            <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <Phone className="w-3 h-3" />
              <span>{phone}</span>
            </div>
          )}
          {selectedCustomer.email && (
            <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <Mail className="w-3 h-3" />
              <span className="truncate max-w-[200px]">{selectedCustomer.email}</span>
            </div>
          )}
          {selectedCustomer.taxId && (
            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">PIN: {selectedCustomer.taxId}</span>
          )}
          {walkin && walkinDetails.name && (
            <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <User className="w-3 h-3" />
              <span className="truncate max-w-[160px]">{walkinDetails.name}</span>
            </div>
          )}
          {walkin && walkinDetails.taxId && (
            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">PIN: {walkinDetails.taxId}</span>
          )}
          {extraFieldDefs
            .filter((f) => (extraFields[f.fieldname] || "").toString().trim())
            .map((f) => (
              <span key={f.fieldname} className="font-mono text-xs text-gray-500 dark:text-gray-400">
                {f.label}: {extraFields[f.fieldname]}
              </span>
            ))}
        </div>
        </div>
      </div>
    )
  ) : (
    <span className={`flex-1 text-sm text-gray-400 dark:text-gray-500 ${bar ? "" : "py-3"}`}>Search or select customer...</span>
  );

  // Warehouse first (where the stock comes from), then price list. A till that cannot switch
  // warehouse still shows which one it sells from, in the same place.
  const pickers = (allowWarehouseChange || fixedWarehouse || allowPriceListSwitching) && (
    <div className={bar ? "flex flex-[2] max-w-md gap-2" : "mt-2 flex gap-2"}>
      {allowWarehouseChange ? (
        <label className={`relative flex-1 ${bar ? "min-w-[7.5rem]" : "min-w-0"}`} title="Warehouse">
          <Warehouse className={PICKER_ICON} aria-hidden />
          <select
            aria-label="Warehouse"
            value={activeWarehouse}
            title={activeWarehouse}
            onChange={(event) => { void handleWarehouseChange(event.target.value); }}
            disabled={isLoadingWarehouses}
            className={PICKER}
          >
            {!activeWarehouse && <option value="">Default Warehouse</option>}
            {warehouses.map((wh) => (
              <option key={wh} value={wh}>{wh}</option>
            ))}
          </select>
        </label>
      ) : fixedWarehouse && (
        <div className={`relative flex-1 ${bar ? "min-w-[7.5rem]" : "min-w-0"}`} title={`Warehouse: ${activeWarehouse}`}>
          <Warehouse className={PICKER_ICON} aria-hidden />
          <span className={`${PICKER} block leading-[34px] bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300`}>{activeWarehouse}</span>
        </div>
      )}
      {allowPriceListSwitching && (
        <label className={`relative flex-1 ${bar ? "min-w-[7.5rem]" : "min-w-0"}`} title="Price list">
          <Tag className={PICKER_ICON} aria-hidden />
          <select
            aria-label="Price list"
            value={activePriceList}
            title={String(activePriceList)}
            onChange={(event) => { void handlePriceListChange(event.target.value); }}
            disabled={isLoadingPriceLists}
            className={PICKER}
          >
            {!activePriceList && <option value="">Default Price List</option>}
            {priceLists.map((priceList) => (
              <option key={priceList.name} value={priceList.name}>
                {priceList.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );

  const sideBtn = `flex-shrink-0 ${bar ? "w-9 rounded-lg" : "w-10 rounded-xl"} border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-beveren-600 dark:text-beveren-400 hover:border-beveren-400 hover:bg-beveren-50 dark:hover:bg-beveren-900/30 transition-colors flex items-center justify-center`;
  const containerClass = bar
    ? "flex min-w-0 flex-1 items-center gap-2"
    : !isMobile ? "relative" : "flex-shrink-0 p-4 border-b border-gray-100 dark:border-gray-700";

  return (
    <div className={containerClass}>
      <div className={`flex items-stretch gap-2 ${bar ? "min-w-[10rem] flex-[3] max-w-md" : ""}`}>
      <div ref={containerRef} className="relative flex-1 min-w-0">
        <div
          id="pos-customer-btn"
          ref={buttonRef}
          onClick={handleOpenDropdown}
          className={`
            flex items-center justify-between w-full gap-2 border cursor-pointer transition-all
            bg-white dark:bg-gray-900
            ${bar ? "h-9 px-3 rounded-lg" : "min-h-[52px] px-4 rounded-xl"}
            ${isOpen
              ? "border-blue-500 ring-2 ring-blue-500/20"
              : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
            }
          `}
        >
          {card}
          <div className="flex shrink-0 items-center gap-1">
            {selectedCustomer && (
              <button
                type="button"
                onClick={handleClear}
                aria-label="Clear customer"
                title="Clear customer"
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            )}
            <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
          </div>
        </div>

        {typeof window !== "undefined" && createPortal(dropdown, document.body)}
      </div>
        {/* Beside the customer in every view: one click, no dropdown to open first. */}
        {canCreateCustomer && (
          <button type="button" onClick={handleAddCustomerClick} className={sideBtn} title="Add New Customer" aria-label="Add New Customer">
            <UserPlus size={18} />
          </button>
        )}
        {selectedCustomer && (
          <button type="button" onClick={() => setAdditionalInfoOpen(true)} className={sideBtn} title="Additional Info (F4)" aria-label="Additional Info">
            <Contact size={18} />
          </button>
        )}
      </div>

      {pickers}

      {showAddCustomerModal && (
        <AddCustomerModal
          customer={null}
          onClose={() => {
            setShowAddCustomerModal(false);
            setPrefilledCustomerName("");
            setPrefilledData({});
          }}
          onSave={handleSaveCustomer}
          prefilledName={prefilledCustomerName}
          prefilledData={prefilledData}
        />
      )}

      <AlertDialog open={warehouseBlocked} onOpenChange={setWarehouseBlocked}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cart has items</AlertDialogTitle>
            <AlertDialogDescription>
              You can't change warehouse while the cart has items. Clear the cart first.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction>OK</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {overdueData && (
        <OverdueWarningModal
          invoices={overdueData.invoices}
          customerName={overdueData.customerName}
          onClose={() => setOverdueData(null)}
        />
      )}
    </div>
  );
};
