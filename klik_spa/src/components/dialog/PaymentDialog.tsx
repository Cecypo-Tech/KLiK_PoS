"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { paymentBlockReason } from "../../utils/paymentBlockReason";
import { usePosShortcutLayer } from "../../hooks/usePosShortcutLayer";
import { getCreditTerms } from "../../services/paymentTerms";
import { chooseTerm, termLabel, type CreditTerms } from "../../utils/creditTerms";
import { Award, Eye, Loader2, MailPlus, MessageCirclePlus, MessageSquarePlus, Printer, RefreshCw, X } from "lucide-react";
import { useCartStore } from "../../stores/cartStore";
import { usePaymentModes } from "../../hooks/usePaymentModes";
import { useSalesTaxCharges } from "../../hooks/useSalesTaxCharges";
import { useShippingRules } from "../../hooks/useShippingRules";
import { selectAllOnFocus } from "../../utils/selectAllOnFocus";
import { formatCartWeight, getCartNetWeight } from "../../utils/cartWeight";
import {
  createDraftSalesInvoice,
  createSalesInvoice,
  discardMpesaDraft,
  DraftNoLongerDraftError,
  getCheckoutRequestStatus,
  previewLoyaltyRedemption,
  submitDraftInvoice,
  validateCheckoutInvoice,
} from "../../services/salesInvoice";
import { checkoutHeldOrder, createHeldOrder, HeldOrderGoneError } from "../../services/salesOrder";
import { heldOrderPayloadExtras, tillFlags } from "../../utils/heldOrderPayload";
import { clearDraftInvoiceCache, forgetOriginalDraftInvoice, forgetOriginalHeldOrder, getOriginalDraftInvoiceId, getOriginalHeldOrderApproval, getOriginalHeldOrderId, getOriginalHeldOrderMpesa, getOriginalOrderDiscountAmount } from "../../utils/draftInvoiceCache";
import { priceApprovalMessage } from "../../utils/priceApproval";
import { heldOrderGoneMessage, staleDraftNotice } from "../../utils/staleDraft";
import { formatCurrencyWithSymbol, getCurrencySymbol } from "../../utils/currency";
import { calculateRemainingAmount, calculateTotalPayments, roundCurrency } from "../../utils/currencyMath";
import {
  appliedFromReceipts,
  isMpesaPaymentMode,
  receiptDraftSubmitData,
  receiptLeftoverMessage,
  uncoveredMpesa,
} from "../../utils/mpesaReceipts";
import { followTotal, toggleOn, trimToPayable, withPaidMpesa } from "../../utils/paymentToggle";
import { taxPreviewStep } from "../../utils/taxPreviewStep";
import { creditSalesAllowed } from "../../utils/creditSales";
import { fetchCustomerCredit, type CustomerCredit } from "../../utils/customerCredit";
import {
  addVoucher,
  appliedTotal,
  resizeVoucher,
  capVouchers,
  customerChangeDropsVouchers,
  labelVoucherAmounts,
  netOfChange,
  voucherApplyAmount,
  vouchersBlockedReason,
  vouchersBlockMpesaReason,
  type AppliedVoucher,
} from "../../utils/voucher";
import { QUEUE_FAILURE_EVENT, watchQueuedCheckout } from "../../utils/queueFailure";
import { cashRefundModes } from "../../utils/returnModes";
import { fetchCustomerRecord, lookupCreditVoucher } from "../../services/voucher";
import { useProductStore } from "../../stores/productStore";
import type { Customer as CartCustomer } from "../../../types";
import VoucherPanel from "./VoucherPanel";
import { nextAllocationTargets, stkAutoSubmitDecision } from "../../utils/stkAutoSubmit";
import {
  AUTO_CHECK_AFTER_MS,
  RECEIPT_GIVE_UP_MESSAGE,
  RECEIPT_PENDING_MESSAGE,
  RECEIPT_POLL_MS,
  autoCheckFor,
  pretickedReceipt,
  pushCheckMessage,
  receiptLookupStep,
  stkReceiptPending,
} from "../../utils/stkPushCheck";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import {
  holdBlockedByMpesa,
  mpesaDraftKeptForStk,
  mpesaDraftToDiscard,
  mpesaOrderToRelease,
  normalizeMpesaStatus,
  resumedMpesaFlow,
  stkRetryAction,
} from "../../utils/mpesaDraftLifecycle";
import {
  attachPushReceipt,
  checkMpesaPush,
  discardMpesaOrder,
  findPushReceipts,
  saveMpesaOrder,
  submitMpesaOrder,
} from "../../services/mpesaOrder";
import { checkoutWasQueued } from "../../utils/checkoutOutcome";
import { openingPaymentAmounts } from "../../utils/paymentDefaults";
import { exclusiveSubtotal } from "../../utils/taxLabel";
import { summaryFigures } from "../../utils/summaryFigures";
import { extractErrorFromException } from "../../utils/errorExtraction";
import { fetchWhatsAppTemplates, getDefaultWhatsAppTemplate, processTemplate, getDefaultMessageTemplate } from "../../services/whatsappTemplateService";
import { fetchEmailTemplates, getDefaultEmailTemplate, processEmailTemplate, getDefaultEmailMessageTemplate } from "../../services/emailTemplateService";
import { getIconAndColor } from "./paymentIcons";
import PaymentHeader from "./PaymentHeader";
import PaymentMethods from "./PaymentMethods";
import SalesPersonSection from "./SalesPersonSection";
import SalespersonAuthModal from "./SalespersonAuthModal";
import TaxSection from "./TaxSection";
import TotalsSection from "./TotalsSection";
import ActionButtons from "./ActionButtons";
import InvoicePreview from "./InvoicePreview";
import SharingInterface from "./SharingInterface";
import DeliveryPersonnelCombobox from "./DeliveryPersonnelCombobox";
import RemarksInput from "./RemarksInput";
import MpesaOptionsModal from "./MpesaOptionsModal";
import OtherCharges from "./OtherCharges";
import StepperInput from "../common/StepperInput";
import type { PaymentDialogProps, PaymentAmount, Calculations, BackendTaxPreview } from "./types";
import { reconcileCheckout } from "../../utils/checkoutReconciliation";
import DisplayPrintPreview from "../../utils/invoicePrint";
import { usePOSProfileStore } from "../../stores/posProfileStore";
import { handlePrintInvoice } from "../../utils/printHandler";
import { qzReprint } from "../../utils/qzPrint";
import QzPrintIcon from "../QzPrintIcon";
import { useSalespersonStore } from "../../stores/salespersonStore";
import {
  getEffectiveDisplayRate as getSharedEffectiveDisplayRate,
  getEffectiveItemRate as getSharedEffectiveItemRate,
} from "../../utils/cartPricing";
import {
  fetchKlikPosStkStatus,
  fetchMpesaRegisterPayments,
  initiateKlikPosStkPush,
  processKlikPosMpesaPayments,
  type MpesaRegisterPayment,
} from "../../services/mpesa";
import {
  clearCheckoutAttempt,
  getCheckoutCartFingerprint,
  getOrCreateCheckoutAttempt,
  markCheckoutAttemptAccepted,
} from "../../utils/checkoutAttempt";

interface MpesaFlowState {
  modeOfPayment: string;
  amount: number;
  phoneNumber: string;
  accountReference: string;
  source: "stk" | "c2b";
  draftInvoiceName?: string;
  requestName?: string;
  checkoutRequestId?: string;
  transactionId?: string;
  status: "idle" | "in_progress" | "completed" | "failed";
  message?: string;
  /** Receipts linked to the draft, each with what it could pay when picked. */
  c2bPayments?: Array<{ name: string; amount: number; transid?: string }>;
}

interface MpesaRealtimeEvent {
  request_name?: string;
  status?: string;
  transaction_id?: string;
}

interface AppliedLoyaltyRedemption {
  loyalty_program: string;
  loyalty_points: number;
  loyalty_amount: number;
}

interface FrappeRealtimeClient {
  on?: (event: string, handler: (data: MpesaRealtimeEvent) => void) => void;
  off?: (event: string, handler: (data: MpesaRealtimeEvent) => void) => void;
}

interface CachedTaxPreviewEntry {
  taxPreview: BackendTaxPreview;
  timestamp: number;
}

interface TemplateAwareCartItem {
  id?: string;
  item_code?: string;
  price?: number;
  quantity: number;
  item_tax_rate?: string | Record<string, number>;
  tax_templates?: Array<{ is_inclusive?: boolean }>;
  total_tax_rate?: number;
}

const TAX_PREVIEW_DEBOUNCE_MS = 350;
const TAX_PREVIEW_CACHE_TTL_MS = 15000;
const TAX_PREVIEW_CACHE_MAX_ENTRIES = 100;

/**
 * The cashier left checkout without finishing the M-Pesa sale: remove the draft M-Pesa made,
 * so it does not sit beside the held order as a second copy of the sale. The server keeps it
 * when an STK push was sent from it - a payment on its way (or made) needs its invoice.
 */
async function discardAbandonedMpesaDraft(invoiceName: string) {
  try {
    const result = await discardMpesaDraft(invoiceName);
    if (result.kept) {
      toast.warning(result.message, { autoClose: 10000, toastId: `mpesa-draft-kept-${invoiceName}` });
    }
  } catch (err) {
    // Kept for another reason (linked elsewhere, queued, not this cashier's): say so, or it
    // sits unnoticed beside the held order.
    toast.warning(err instanceof Error ? err.message : `Draft ${invoiceName} was kept.`, {
      autoClose: 10000,
      toastId: `mpesa-draft-kept-${invoiceName}`,
    });
  }
}

/**
 * The cashier left checkout with the M-Pesa sale unfinished: hand its order back. The server
 * deletes it, or keeps it as a held order when a push sent from it may still pay - say so, or
 * the cashier may charge the customer again.
 */
async function discardAbandonedMpesaOrder(orderName: string) {
  try {
    const result = await discardMpesaOrder(orderName);
    if (result.kept) {
      toast.warning(result.message, { autoClose: 15000, toastId: `mpesa-order-kept-${orderName}` });
    }
  } catch (err) {
    toast.warning(err instanceof Error ? err.message : `Order ${orderName} was kept.`, {
      autoClose: 10000,
      toastId: `mpesa-order-kept-${orderName}`,
    });
  }
}

/** The applied vouchers' total inside the payment amounts. It is never a payment row and
never a real Mode of Payment name: buildPaymentData sends the vouchers themselves as
customerCredit, which the server settles after submit. */
const CUSTOMER_CREDIT_METHOD = "__klik_vouchers__";

export default function PaymentDialog(props: PaymentDialogProps) {
  const {
    isOpen,
    onClose,
    cartItems,
    appliedCoupons,
    selectedCustomer,
    onHoldOrder,
    isMobile = false,
    isFullPage = false,
    backLabel = "Back",
    initialSharingMode = null,
    externalInvoiceData = null,
    itemDiscounts = {},
  } = props;

  const [selectedSalesTaxCharges, setSelectedSalesTaxCharges] = useState("");
  const [paymentAmounts, setPaymentAmounts] = useState<PaymentAmount>({});
  const [customerCredit, setCustomerCredit] = useState<CustomerCredit | null>(null);
  const [appliedVouchers, setAppliedVouchers] = useState<AppliedVoucher[]>([]);
  const [voucherPanelOpen, setVoucherPanelOpen] = useState(false);
  const [activeMethodId, setActiveMethodId] = useState<string | null>(null);
  const [lastModifiedMethodId, setLastModifiedMethodId] = useState<string | null>(null);
  const [paymentReferences, setPaymentReferences] = useState<Record<string, string>>({});
  const [isProcessingPayment, setIsProcessingPayment] = useState(false);
  const [isHoldingOrder, setIsHoldingOrder] = useState(false);
  const [invoiceSubmitted, setInvoiceSubmitted] = useState(false);
  // What the server did with the sale - not what the background checkbox asked for.
  const [submissionQueued, setSubmissionQueued] = useState(false);
  const [isCreditSale, setIsCreditSale] = useState(false);
  const [dueDate, setDueDate] = useState("");
  // Payment terms in place of a typed due date, where the site has any (utils/creditTerms).
  const [creditTerms, setCreditTerms] = useState<CreditTerms | null>(null);
  const [termsTemplate, setTermsTemplate] = useState("");
  const [creditTermsLoading, setCreditTermsLoading] = useState(false);
  // The cashier's own pick survives a refetch (Credit Sale off and on); a new customer gets
  // their own terms preselected instead.
  const handPickedTerm = useRef<{ customer: string | undefined; name: string } | null>(null);
  const usingTerms = isCreditSale && (creditTerms?.templates.length ?? 0) > 0;
  const [submittedInvoice, setSubmittedInvoice] = useState<any>(null);
  const [invoiceData, setInvoiceData] = useState<any>(null);
  const [isAutoPrinting, setIsAutoPrinting] = useState(false);
  const [sharingMode, setSharingMode] = useState<string | null>(initialSharingMode);
  const [sharingData, setSharingData] = useState({
    email: selectedCustomer?.email || "",
    phone: selectedCustomer?.phone || "",
    name: selectedCustomer?.name || "",
  });
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [isSendingWhatsapp, setIsSendingWhatsapp] = useState(false);
  const [whatsappTemplates, setWhatsappTemplates] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [customMessage, setCustomMessage] = useState("");
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const [isEditingWhatsapp, setIsEditingWhatsapp] = useState(false);
  const [emailTemplates, setEmailTemplates] = useState<any[]>([]);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState<any>(null);
  const [emailMessage, setEmailMessage] = useState("");
  const [isLoadingEmailTemplates, setIsLoadingEmailTemplates] = useState(false);
  const [isEditingEmail, setIsEditingEmail] = useState(false);
  const [showSalespersonModal, setShowSalespersonModal] = useState(false);
  const [selectedDeliveryPersonnel, setSelectedDeliveryPersonnel] = useState<string | null>(null);
  const [remarks, setRemarks] = useState("");
  const [deliveryCharge, setDeliveryCharge] = useState(0);
  const [orderDiscountAmount, setOrderDiscountAmount] = useState(0);
  const [orderDiscountPercentInput, setOrderDiscountPercentInput] = useState(0);
  const [backendTaxPreview, setBackendTaxPreview] = useState<BackendTaxPreview | null>(null);
  const [isTaxPreviewLoading, setIsTaxPreviewLoading] = useState(false);
  const [, setTaxPreviewError] = useState<string | null>(null);
  const [mpesaFlow, setMpesaFlow] = useState<MpesaFlowState | null>(null);
  // The push "Check with M-Pesa" is offered for: set once the till's own check has run on it.
  const [checkOfferedFor, setCheckOfferedFor] = useState<string | null>(null);
  const [isCheckingMpesa, setIsCheckingMpesa] = useState(false);
  // A paid push's receipt: the matches the lookup found, and the push it stopped looking for.
  const [pushReceipts, setPushReceipts] = useState<MpesaRegisterPayment[]>([]);
  const [receiptLookupEndedFor, setReceiptLookupEndedFor] = useState<string | null>(null);
  const [mpesaDraftInvoiceName, setMpesaDraftInvoiceName] = useState<string | null>(null);
  // The draft Sales Order STK pushes are sent from (klik_pos.api.mpesa_order), until submit.
  const [mpesaOrderName, setMpesaOrderName] = useState<string | null>(null);
  // Set once a push is sent from it in this dialog: only then does leaving checkout let it go.
  // A kept order resumed and closed again without a new push stays as it was, on the Held tab.
  const unfinishedMpesaOrderRef = useRef<string | null>(null);
  // The M-Pesa draft not yet submitted, read when the dialog closes or unmounts.
  const unfinishedMpesaDraftRef = useRef<string | null>(null);
  // Draft creation, STK initiation, receipt reconcile or submit still running.
  const mpesaWorkInFlightRef = useRef(0);
  // Drafts an STK push was sent from: the dialog never discards these.
  const stkSentFromRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    unfinishedMpesaDraftRef.current = mpesaDraftInvoiceName;
  }, [mpesaDraftInvoiceName]);
  const releaseUnfinishedMpesaDraft = useCallback(() => {
    const order = mpesaOrderToRelease(unfinishedMpesaOrderRef.current, mpesaWorkInFlightRef.current);
    unfinishedMpesaOrderRef.current = null;
    if (order) void discardAbandonedMpesaOrder(order);

    const checkout = {
      draftName: unfinishedMpesaDraftRef.current,
      workInFlight: mpesaWorkInFlightRef.current,
      stkSentFrom: stkSentFromRef.current,
    };
    unfinishedMpesaDraftRef.current = null;
    const keptForStk = mpesaDraftKeptForStk(checkout);
    if (keptForStk) {
      toast.warning(keptForStk, { autoClose: 15000, toastId: `mpesa-draft-kept-${checkout.draftName}` });
      return;
    }
    const abandoned = mpesaDraftToDiscard(checkout);
    if (abandoned) void discardAbandonedMpesaDraft(abandoned);
  }, []);
  // On the main POS screen the dialog unmounts rather than closing.
  useEffect(() => () => releaseUnfinishedMpesaDraft(), [releaseUnfinishedMpesaDraft]);
  // This sale turned out to be recorded already, as this invoice; Submit stays blocked.
  const [alreadySubmittedAs, setAlreadySubmittedAs] = useState<string | null>(null);
  // Only the mobile overlay can be dismissed; unticking M-Pesa resets it.
  const [mpesaPanelDismissed, setMpesaPanelDismissed] = useState(false);
  const mpesaOptionsPanelRef = useRef<HTMLDivElement | null>(null);
  const [mpesaPhoneNumber, setMpesaPhoneNumber] = useState(selectedCustomer?.phone || "");
  const [mpesaSearchTerm, setMpesaSearchTerm] = useState("");
  const [mpesaRegisterPayments, setMpesaRegisterPayments] = useState<MpesaRegisterPayment[]>([]);
  const [mpesaRegisterCount, setMpesaRegisterCount] = useState(0);
  const [selectedMpesaPayments, setSelectedMpesaPayments] = useState<MpesaRegisterPayment[]>([]);
  const [isLoadingMpesaRegisterPayments, setIsLoadingMpesaRegisterPayments] = useState(false);
  const [loyaltyPointsInput, setLoyaltyPointsInput] = useState("");
  const [appliedLoyalty, setAppliedLoyalty] = useState<AppliedLoyaltyRedemption | null>(null);
  const [isApplyingLoyalty, setIsApplyingLoyalty] = useState(false);
  const backendTaxPreviewRef = useRef<BackendTaxPreview | null>(null);
  const taxPreviewRequestIdRef = useRef(0);
  // The debounce is for typing. Opening checkout and picking from a list (a shipping rule)
  // skip it: those are single decisions, and the debounce alone was most of the wait.
  const taxPreviewImmediateRef = useRef(true);
  // Preview requests on their way, by cache key. While checkout opens, payment modes and
  // other lookups land and re-run the preview effect; without this each re-run discarded the
  // answer already in flight, waited out the debounce and asked the server the same thing.
  const taxPreviewInFlightRef = useRef<Map<string, ReturnType<typeof validateCheckoutInvoice>>>(new Map());
  const taxPreviewCacheRef = useRef<Map<string, CachedTaxPreviewEntry>>(new Map());
  const initializedCreditDefaultRef = useRef(false);
  const initializedOrderDiscountRef = useRef(false);
  // State, not a ref: the write-back below must wait for the render that holds the restored
  // values, or it would store the pre-restore ones first.
  const [checkoutExtrasRestored, setCheckoutExtrasRestored] = useState(false);

  const { posDetails } = usePOSProfileStore();
  const posLoading = false;
  const {
    activeSalesperson: currentSalesperson,
    rememberLocked: rememberSalesperson,
    ensureInitialized,
    isRestoring: isSalespersonRestoring,
    isVerifying: isVerifyingPin,
    clearActiveSalesperson,
  } = useSalespersonStore();
  const { modes, isLoading, error } = usePaymentModes(typeof posDetails?.name === "string" ? posDetails.name : "");
  const { salesTaxCharges, defaultTax, isLoading: salesTaxLoading } = useSalesTaxCharges();
  const navigate = useNavigate();
  const { clearCart, walkinDetails, extraFields, shippingRule, setShippingRule, checkoutExtras, setCheckoutExtras } = useCartStore();
  const posProfileName = typeof posDetails?.name === "string" ? posDetails.name : "";
  const posCompanyName =
    typeof posDetails?.company === "string"
      ? posDetails.company
      : typeof posDetails?.company?.name === "string"
        ? posDetails.company.name
        : "";

  // Open credit notes this customer can spend as a tender (the credit router).
  // Walk In never sees it - nobody can prove that credit is theirs later.
  useEffect(() => {
    let cancelled = false;
    const customerId = selectedCustomer?.id || selectedCustomer?.name;
    if (!isOpen || !customerId || !posCompanyName || selectedCustomer?.isWalkin) {
      setCustomerCredit(null);
      return;
    }
    const tillCurrency = typeof posDetails?.currency === "string" ? posDetails.currency : undefined;
    fetchCustomerCredit(String(customerId), posCompanyName, tillCurrency)
      .then((credit) => {
        if (!cancelled) setCustomerCredit(credit);
      })
      .catch(() => {
        if (!cancelled) setCustomerCredit(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedCustomer, posCompanyName, posDetails?.currency]);

  // A credit sale, an M-Pesa order or an older draft carries no vouchers: those paths
  // settle no credit, so the figures must stop counting them.
  const vouchersBlocked = vouchersBlockedReason({
    isCreditSale,
    mpesaOrder: Boolean(mpesaOrderName || mpesaDraftInvoiceName),
    editingDraft: Boolean(getOriginalDraftInvoiceId()),
  });
  useEffect(() => {
    if (!vouchersBlocked || appliedVouchers.length === 0) return;
    setAppliedVouchers([]);
    // Only when the total is still there: Credit Sale has already emptied the amounts, and an
    // empty set is what lets the till's opening amount come back when it is unticked.
    setPaymentAmounts((prev) =>
      (prev[CUSTOMER_CREDIT_METHOD] || 0) > 0 ? { ...prev, [CUSTOMER_CREDIT_METHOD]: 0 } : prev
    );
    toast.info(`Vouchers removed: ${vouchersBlocked}.`);
  }, [vouchersBlocked, appliedVouchers.length]);

  // Applied vouchers belong to the sale's customer: a new customer starts them over rather than
  // Submit refusing them. The panel keeps a looked-up voucher, so "Switch sale" then Apply works.
  const saleCustomerId = selectedCustomer?.id || selectedCustomer?.name || null;
  const voucherCustomerRef = useRef<string | null>(null);
  useEffect(() => {
    const previous = voucherCustomerRef.current;
    voucherCustomerRef.current = saleCustomerId;
    if (!customerChangeDropsVouchers(previous, saleCustomerId, appliedVouchers.length, invoiceSubmitted)) return;
    setAppliedVouchers([]);
    setPaymentAmounts((prev) =>
      (prev[CUSTOMER_CREDIT_METHOD] || 0) > 0 ? { ...prev, [CUSTOMER_CREDIT_METHOD]: 0 } : prev
    );
    toast.info("Vouchers removed: the sale's customer changed.");
  }, [saleCustomerId, appliedVouchers.length, invoiceSubmitted]);

  const isB2B = posDetails?.business_type === "B2B";
  const isB2C = posDetails?.business_type === "B2C";
  const print_receipt_on_order_complete = posDetails?.print_receipt_on_order_complete;
  const deliveryRequiredValue = posDetails?.custom_delivery_required;
  const isDeliveryRequired = deliveryRequiredValue === 1;
  const isDeliveryChargeEnabled =
    posDetails?.custom_enable_delivery_charge === 1
    || posDetails?.custom_enable_delivery_charge === "1"
    || posDetails?.custom_enable_delivery_charge === true;
  const deliveryChargeItemCode =
    typeof posDetails?.custom_delivery_charge_item === "string"
      ? posDetails.custom_delivery_charge_item
      : "";
  const allowDiscountChange =
    posDetails?.allow_discount_change === 1
    || posDetails?.allow_discount_change === "1"
    || posDetails?.allow_discount_change === true;
  const allowPartialPayments = Boolean(posDetails?.allow_partial_payment);
  const allowCreditSales = creditSalesAllowed(posDetails);
  const requiresSalespersonPin = !!posDetails?.custom_sales_person_pin_required;
  const allow_holding_invoices = Boolean(posDetails?.allow_holding_invoices);
  const isShippingRuleEnabled =
    posDetails?.custom_enable_shipping_rule === 1
    || posDetails?.custom_enable_shipping_rule === "1"
    || posDetails?.custom_enable_shipping_rule === true;
  // The store survives a hold and recall; a till with the feature off never sends one.
  const activeShippingRule = isShippingRuleEnabled ? shippingRule : null;
  const { rules: shippingRules } = useShippingRules(isShippingRuleEnabled);

  useEffect(() => {
    // The server refuses a rule and a delivery charge together - delivery would be paid twice.
    if (activeShippingRule && deliveryCharge > 0) setDeliveryCharge(0);
  }, [activeShippingRule, deliveryCharge]);
  const isTaxIncludedInBasicRate =
    posDetails?.is_tax_included_in_basic_rate === 1
    || posDetails?.is_tax_included_in_basic_rate === "1"
    || posDetails?.is_tax_included_in_basic_rate === true;
  const autoAllocateRemainingPayment =
    posDetails?.custom_auto_allocate_remaining_payment === 1 ||
    posDetails?.custom_auto_allocate_remaining_payment === "1" ||
    posDetails?.custom_auto_allocate_remaining_payment === true;

  const defaultSalesType = useMemo(() => {
    const rawValue = typeof posDetails?.default_sales_type === "string"
      ? posDetails.default_sales_type
      : "Cash";
    return rawValue.trim().toLowerCase();
  }, [posDetails?.default_sales_type]);

  const [enableBackgroundSubmission, setEnableBackgroundSubmission] = useState<boolean>(
    Boolean(posDetails?.enable_background_invoice_submission)
  );

  useEffect(() => {
    setEnableBackgroundSubmission(Boolean(posDetails?.enable_background_invoice_submission));
  }, [posDetails?.enable_background_invoice_submission]);

  const displayCurrencySymbol = useMemo(() => {
    const invoiceSymbol = typeof invoiceData?.currency_symbol === "string" ? invoiceData.currency_symbol.trim() : "";
    if (invoiceSymbol) return invoiceSymbol;
    const invoiceCurrency = typeof invoiceData?.currency === "string" ? invoiceData.currency.trim() : "";
    if (invoiceCurrency) return getCurrencySymbol(invoiceCurrency);
    const externalInvoiceSymbol = typeof externalInvoiceData?.currency_symbol === "string" ? externalInvoiceData.currency_symbol.trim() : "";
    if (externalInvoiceSymbol) return externalInvoiceSymbol;
    const externalInvoiceCurrency = typeof externalInvoiceData?.currency === "string" ? externalInvoiceData.currency.trim() : "";
    if (externalInvoiceCurrency) return getCurrencySymbol(externalInvoiceCurrency);
    const companyDefaultCurrency = typeof posDetails?.company?.default_currency === "string" ? posDetails.company.default_currency.trim() : "";
    if (companyDefaultCurrency) return getCurrencySymbol(companyDefaultCurrency);
    const posCurrencySymbol = typeof posDetails?.currency_symbol === "string" ? posDetails.currency_symbol.trim() : "";
    if (posCurrencySymbol) return posCurrencySymbol;
    const posCurrency = typeof posDetails?.currency === "string" ? posDetails.currency.trim() : "";
    if (posCurrency) return getCurrencySymbol(posCurrency);
    return "$";
  }, [invoiceData, externalInvoiceData, posDetails]);

  const selectedTaxTemplate = useMemo(
    () => salesTaxCharges.find((tax) => tax.id === selectedSalesTaxCharges) || null,
    [salesTaxCharges, selectedSalesTaxCharges]
  );

  const selectedTaxLineMap = useMemo(() => {
    const map = new Map<string, { charge_type?: string; rate?: number; included_in_print_rate?: boolean }>();
    for (const line of selectedTaxTemplate?.tax_lines || []) {
      if (!line.account_head) continue;
      map.set(line.account_head, line);
    }
    return map;
  }, [selectedTaxTemplate]);

  const getEffectiveItemRate = useCallback((item: TemplateAwareCartItem) => {
    return getSharedEffectiveItemRate(item, {
      itemDiscounts,
      isTaxIncludedInBasicRate,
      selectedTaxLineMap,
      selectedTaxTemplate,
    });
  }, [isTaxIncludedInBasicRate, itemDiscounts, selectedTaxLineMap, selectedTaxTemplate]);

  const getEffectiveDisplayRate = useCallback((item: TemplateAwareCartItem) => {
    return getSharedEffectiveDisplayRate(item, {
      itemDiscounts,
      isTaxIncludedInBasicRate,
      selectedTaxLineMap,
      selectedTaxTemplate,
    });
  }, [isTaxIncludedInBasicRate, itemDiscounts, selectedTaxLineMap, selectedTaxTemplate]);

  const calculations: Calculations = useMemo(() => {
    // subtotal uses exclusive (pre-tax) prices so the tax line is separately visible
    const subtotal = cartItems.reduce((sum, item) => {
      return roundCurrency(sum + roundCurrency(getEffectiveItemRate(item) * item.quantity));
    }, 0);
    const couponDiscount = appliedCoupons.reduce((sum, coupon) => roundCurrency(sum + coupon.value), 0);
    const taxableAmount = roundCurrency(Math.max(0, subtotal - couponDiscount - orderDiscountAmount));
    const selectedTax = selectedTaxTemplate;
    const taxRate = selectedTax?.rate || 0;
    const isInclusive = isTaxIncludedInBasicRate || selectedTax?.is_inclusive || false;
    let taxAmount: number;
    let grandTotal: number;
    if (isInclusive) {
      taxAmount = roundCurrency((taxableAmount * taxRate) / (100 + taxRate));
      grandTotal = taxableAmount;
    } else {
      taxAmount = roundCurrency((taxableAmount * taxRate) / 100);
      grandTotal = roundCurrency(taxableAmount + taxAmount);
    }
    return {
      subtotal,
      couponDiscount,
      orderDiscountAmount,
      taxableAmount,
      taxAmount,
      grandTotal: roundCurrency(grandTotal),
      selectedTax,
      isInclusive,
    };
  }, [cartItems, appliedCoupons, getEffectiveItemRate, isTaxIncludedInBasicRate, selectedTaxTemplate, orderDiscountAmount]);

  useEffect(() => {
    if (!allowDiscountChange) {
      setOrderDiscountAmount(0);
      setOrderDiscountPercentInput(0);
    }
  }, [allowDiscountChange]);

  const handleOrderDiscountAmountChange = (value: number) => {
    const amt = Math.max(0, value || 0);
    setOrderDiscountAmount(amt);
    setOrderDiscountPercentInput(
      calculations.subtotal > 0 ? parseFloat(((amt / calculations.subtotal) * 100).toFixed(2)) : 0
    );
  };

  const handleOrderDiscountPercentChange = (value: number) => {
    const pct = Math.min(100, Math.max(0, value || 0));
    const amt = roundCurrency((calculations.subtotal * pct) / 100);
    setOrderDiscountPercentInput(pct);
    setOrderDiscountAmount(amt);
  };

  // Restore an order-level discount carried over from a resumed held order or
  // edited draft invoice — otherwise it silently resets to 0 on reopen and
  // gets wiped from the invoice on the next save/submit.
  useEffect(() => {
    if (!isOpen) {
      initializedOrderDiscountRef.current = false;
      return;
    }
    if (initializedOrderDiscountRef.current) {
      return;
    }
    if (allowDiscountChange) {
      // The cart store carries it across closing checkout and a hold/recall; a recalled
      // draft invoice still brings it in the draft cache.
      const restoredDiscount =
        checkoutExtras.orderDiscountAmount
        || (getOriginalHeldOrderId() || getOriginalDraftInvoiceId() ? getOriginalOrderDiscountAmount() : 0);
      if (restoredDiscount > 0) {
        handleOrderDiscountAmountChange(restoredDiscount);
      }
    }
    initializedOrderDiscountRef.current = true;
  }, [isOpen, allowDiscountChange]);

  // Delivery charge and person and the tax template come back from the cart store each time
  // checkout opens - after closing it, and after recalling a held order.
  useEffect(() => {
    if (!isOpen) {
      setCheckoutExtrasRestored(false);
      return;
    }
    if (checkoutExtrasRestored) return;
    if (checkoutExtras.deliveryCharge > 0 && isDeliveryChargeEnabled && !activeShippingRule) {
      setDeliveryCharge(checkoutExtras.deliveryCharge);
    }
    if (checkoutExtras.deliveryPersonnel) setSelectedDeliveryPersonnel(checkoutExtras.deliveryPersonnel);
    if (checkoutExtras.salesTaxCharges) setSelectedSalesTaxCharges(checkoutExtras.salesTaxCharges);
    setRemarks(checkoutExtras.remarks || "");
    setCheckoutExtrasRestored(true);
    // Once per open, from what the store held at that moment - not on every store write.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // ...and go back to it as they change, so a hold from the cart sends what checkout showed.
  useEffect(() => {
    if (!isOpen || !checkoutExtrasRestored) return;
    setCheckoutExtras({
      deliveryCharge: Number(deliveryCharge) || 0,
      deliveryPersonnel: selectedDeliveryPersonnel,
      orderDiscountAmount: Number(orderDiscountAmount) || 0,
      salesTaxCharges: selectedSalesTaxCharges,
      remarks,
    });
    // setCheckoutExtras is a stable store action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, checkoutExtrasRestored, deliveryCharge, selectedDeliveryPersonnel, orderDiscountAmount, selectedSalesTaxCharges, remarks]);

  // Inclusive grand total: sum of discountedPriceIncl (already computed correctly in OrderSummary mapping)
  // This is reliable regardless of whether items have ERPNext Item Tax Templates
  const inclGrandTotal = useMemo(() => {
    const itemTotal = cartItems.reduce((sum, item) => {
      return roundCurrency(sum + roundCurrency(getEffectiveDisplayRate(item) * item.quantity));
    }, 0);
    return roundCurrency(itemTotal + Number(deliveryCharge || 0));
  }, [cartItems, deliveryCharge, getEffectiveDisplayRate]);

  const totalPaidAmount = calculateTotalPayments(Object.values(paymentAmounts));
  const hasNegativePaymentAmount = Object.values(paymentAmounts).some((amount) => amount < 0);
  const backendTaxLines = backendTaxPreview?.tax_breakdown || [];
  const hasBackendTaxPreview = backendTaxPreview !== null;
  const hasBackendTaxBreakdown = backendTaxLines.length > 0;
  const backendRoundedTotal = roundCurrency(Number(backendTaxPreview?.rounded_total || 0));
  const backendGrandTotal = roundCurrency(Number(backendTaxPreview?.grand_total || inclGrandTotal));
  const checkoutGrandTotal = hasBackendTaxPreview
    ? backendTaxPreview?.disable_rounded_total === 0 && backendRoundedTotal > 0
      ? backendRoundedTotal
      : backendGrandTotal
    : roundCurrency(inclGrandTotal);
  const loyaltyAmount = Number(appliedLoyalty?.loyalty_amount || 0);
  const checkoutPayableTotal = roundCurrency(Math.max(0, checkoutGrandTotal - loyaltyAmount));
  const outstandingAmount = calculateRemainingAmount(checkoutPayableTotal, Object.values(paymentAmounts));

  // Tax amount = inclusive grand total minus exclusive subtotal (works for both item templates and global taxes)
  const localTaxTotal = roundCurrency(checkoutGrandTotal - calculations.subtotal - (calculations.couponDiscount > 0 ? 0 : 0));

  // Before tax, always: the summary reads Subtotal + Tax = Grand Total. The server's
  // net_total already is; the local figure carries the tax inside on an inclusive till.
  const localSubtotal = exclusiveSubtotal(
    calculations.subtotal,
    calculations.isInclusive,
    calculations.selectedTax?.rate ?? null,
  );
  // A Shipping Rule's charge is a row in the taxes table, but it is not tax.
  const shippingAmount = hasBackendTaxPreview ? roundCurrency(Number(backendTaxPreview?.shipping_amount || 0)) : 0;
  const serverFigures = hasBackendTaxPreview
    ? summaryFigures({
        netTotal: Number(backendTaxPreview?.net_total || 0),
        taxTotal: Number(backendTaxPreview?.total_taxes_and_charges || 0),
        grandTotal: Number(backendTaxPreview?.grand_total || 0),
        discount: Number(backendTaxPreview?.discount_amount || 0),
        shipping: shippingAmount,
      })
    : null;
  const displaySubtotal = serverFigures && serverFigures.subtotal > 0 ? serverFigures.subtotal : localSubtotal;
  // Before tax too, so Subtotal - Discount + Tax = Grand Total. The local figure is the
  // entered amounts; it is only used while the server's preview is missing.
  const displayDiscount = serverFigures
    ? serverFigures.discount
    : roundCurrency((calculations.couponDiscount || 0) + (calculations.orderDiscountAmount || 0));
  const displayTaxIsIncluded = hasBackendTaxBreakdown
    ? backendTaxLines.some((line) => Number(line.included_in_print_rate) === 1)
    : calculations.isInclusive;
  const displayTaxTotal = hasBackendTaxPreview
    ? roundCurrency(Math.max(0, Number(backendTaxPreview?.total_taxes_and_charges || 0) - shippingAmount))
    : calculations.taxAmount > 0 ? calculations.taxAmount : Math.max(0, localTaxTotal);
  const cartNetWeight = useMemo(() => getCartNetWeight(cartItems), [cartItems]);
  const netWeightTotal =
    hasBackendTaxPreview && backendTaxPreview?.total_net_weight !== undefined
      ? Number(backendTaxPreview.total_net_weight || 0)
      : cartNetWeight.total;
  const netWeightLabel = netWeightTotal > 0 ? formatCartWeight({ ...cartNetWeight, total: netWeightTotal }) : "";

  // The receipt's lines come from this cart; its Subtotal, Tax and Total come from the
  // server preview. If the server priced a line differently, the printed lines will not
  // add up to the printed total and the customer pays the server's number. Stop instead.
  const reconciliation = useMemo(() => {
    const previewLines = backendTaxPreview?.items;
    if (!previewLines || previewLines.length === 0) {
      return { ok: true, message: null as string | null, extraCharges: [] };
    }
    const cartLines = cartItems.map((item) => ({
      item_code: item.item_code || item.id,
      qty: Number(item.quantity || 0),
      rate: Number(getEffectiveItemRate(item as TemplateAwareCartItem) || 0),
    }));
    return reconcileCheckout(cartLines, previewLines);
  }, [backendTaxPreview, cartItems, getEffectiveItemRate]);
  
  const previousCheckoutGrandTotalRef = useRef(checkoutPayableTotal);

  const toggleCreditSale = () => {
    if (stkLockedMethod) {
      toast.error("An M-Pesa push is pending or paid on this sale - it cannot become a credit sale.");
      return;
    }
    setIsCreditSale((prev) => {
      if (!prev) setPaymentAmounts({});
      return !prev;
    });
  };

  const currentDate = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const paymentMethods = useMemo(() => {
    const sortedModes = [...modes].sort((a, b) => {
      if (a.idx !== undefined && b.idx !== undefined) {
        return a.idx - b.idx;
      }
      if (a.default === 1 && b.default !== 1) return -1;
      if (a.default !== 1 && b.default === 1) return 1;
      return 0;
    });
    const rows = sortedModes.map((mode) => {
      const { icon, color } = getIconAndColor(mode.type || "Default");
      return {
        id: mode.mode_of_payment,
        name: mode.mode_of_payment,
        icon,
        color,
        enabled: true,
        amount: paymentAmounts[mode.mode_of_payment] || 0,
        type: mode.type || "",
        isDefault: mode.default === 1,
        idx: mode.idx,
      };
    });
    return rows;
  }, [modes, paymentAmounts]);

  const orderedPaymentMethodIds = useMemo(() => {
    const sortedModes = [...modes].sort((a, b) => {
      if (a.idx !== undefined && b.idx !== undefined) {
        return a.idx - b.idx;
      }
      if (a.default === 1 && b.default !== 1) return -1;
      if (a.default !== 1 && b.default === 1) return 1;
      return 0;
    });

    return sortedModes.map((mode) => mode.mode_of_payment);
  }, [modes]);

  const getActiveMpesaPayment = useCallback(() => {
    const entries = Object.entries(paymentAmounts).filter(([, amount]) => (amount || 0) > 0);
    for (const [method, amount] of entries) {
      const mode = modes.find((m) => m.mode_of_payment === method);
      if (isMpesaPaymentMode(mode, method)) {
        return {
          method,
          amount: Number(amount || 0),
        };
      }
    }
    return null;
  }, [modes, paymentAmounts]);

  const activeMpesaMethod = getActiveMpesaPayment()?.method ?? null;
  const hasActiveMpesaPayment = activeMpesaMethod !== null;
  // Ticking an M-Pesa row is the trigger: the panel follows it, no separate button.
  const showMpesaPanel = hasActiveMpesaPayment && !invoiceSubmitted && !mpesaPanelDismissed;

  // An STK push in flight or paid is money the customer was asked for or has sent: its row
  // cannot be edited, re-apportioned, trimmed or unticked, and nothing may wipe it.
  const stkLockedMethod =
    mpesaFlow?.source === "stk" &&
    (mpesaFlow.status === "in_progress" || mpesaFlow.status === "completed") &&
    !invoiceSubmitted
      ? mpesaFlow.modeOfPayment
      : null;
  // Paid and not yet submitted: leaving takes an explicit confirmation.
  const stkPaidMethod = stkLockedMethod && mpesaFlow?.status === "completed" ? stkLockedMethod : null;
  // Safaricom said paid without a receipt number: nothing submits until the receipt is attached.
  const receiptPending = stkReceiptPending(mpesaFlow) && !invoiceSubmitted;

  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false);
  const closeDialog = useCallback(
    (completed?: boolean) => {
      if (!completed && stkPaidMethod) {
        setLeaveConfirmOpen(true);
        return;
      }
      onClose(completed);
    },
    [onClose, stkPaidMethod]
  );

  useEffect(() => {
    if (!hasActiveMpesaPayment) setMpesaPanelDismissed(false);
  }, [hasActiveMpesaPayment]);

  const trimPaymentAmountsToPayable = useCallback((payableTotal: number) => {
    setPaymentAmounts((prev) => {
      const preferredIds = [
        lastModifiedMethodId,
        activeMethodId,
        ...Object.entries(prev)
          .filter(([, amount]) => (amount || 0) > 0)
          .map(([methodId]) => methodId),
      ].filter((methodId, index, all): methodId is string => Boolean(methodId) && all.indexOf(methodId) === index);
      return trimToPayable(prev, payableTotal, preferredIds, [CUSTOMER_CREDIT_METHOD, ...(stkLockedMethod ? [stkLockedMethod] : [])]);
    });
  }, [activeMethodId, lastModifiedMethodId, stkLockedMethod]);

  const clearLoyaltyRedemption = useCallback(() => {
    setAppliedLoyalty(null);
    setLoyaltyPointsInput("");
  }, []);

  const handleLoyaltyPointsInputChange = useCallback((value: string) => {
    setLoyaltyPointsInput(value);

    const loyalty = selectedCustomer?.loyalty;
    const points = Number.parseInt(value || "0", 10);
    const availablePoints = Number(loyalty?.available_points ?? loyalty?.loyalty_points ?? 0);
    const conversionFactor = Number(loyalty?.conversion_factor || 0);

    if (!loyalty?.enabled || !loyalty.loyalty_program || !Number.isFinite(points) || points <= 0) {
      setAppliedLoyalty(null);
      return;
    }

    if (points > availablePoints || conversionFactor <= 0) {
      setAppliedLoyalty(null);
      return;
    }

    const loyaltyAmount = roundCurrency(Math.min(points * conversionFactor, checkoutGrandTotal));
    setAppliedLoyalty({
      loyalty_program: loyalty.loyalty_program,
      loyalty_points: points,
      loyalty_amount: loyaltyAmount,
    });
    trimPaymentAmountsToPayable(roundCurrency(Math.max(0, checkoutGrandTotal - loyaltyAmount)));
  }, [checkoutGrandTotal, selectedCustomer?.loyalty, trimPaymentAmountsToPayable]);

  const handleApplyLoyaltyRedemption = useCallback(async () => {
    if (stkLockedMethod) {
      // Redeeming now would cut the sale below what the customer was asked to pay.
      toast.error("Redeem loyalty points before sending the M-Pesa push.");
      return;
    }
    const loyalty = selectedCustomer?.loyalty;
    const points = Number.parseInt(loyaltyPointsInput || "0", 10);

    if (!selectedCustomer?.id || !loyalty?.enabled || !loyalty.loyalty_program) {
      toast.error("Selected customer is not enrolled in a loyalty program.");
      return;
    }

    if (!Number.isFinite(points) || points <= 0) {
      toast.error("Enter loyalty points greater than zero.");
      return;
    }

    if (points > Number(loyalty.available_points ?? loyalty.loyalty_points ?? 0)) {
      toast.error("Entered points exceed the customer's available loyalty balance.");
      return;
    }

    try {
      setIsApplyingLoyalty(true);
      const preview = await previewLoyaltyRedemption(
        selectedCustomer.id,
        points,
        checkoutGrandTotal,
        posCompanyName || undefined,
        loyalty.loyalty_program,
      );

      setAppliedLoyalty({
        loyalty_program: preview.loyalty_program,
        loyalty_points: preview.loyalty_points,
        loyalty_amount: Number(preview.loyalty_amount || 0),
      });
      const newPayableTotal = roundCurrency(Math.max(0, checkoutGrandTotal - Number(preview.loyalty_amount || 0)));
      trimPaymentAmountsToPayable(newPayableTotal);
      toast.success("Loyalty redemption applied.");
    } catch (error) {
      setAppliedLoyalty(null);
      toast.error(extractErrorFromException(error, "Failed to apply loyalty redemption"));
    } finally {
      setIsApplyingLoyalty(false);
    }
  }, [checkoutGrandTotal, loyaltyPointsInput, posCompanyName, selectedCustomer, trimPaymentAmountsToPayable, stkLockedMethod]);

  const refreshMpesaStatus = useCallback(async (requestName?: string) => {
    const name = requestName || mpesaFlow?.requestName;
    if (!name) return;
    try {
      const statusResponse = await fetchKlikPosStkStatus(name);
      const normalizedStatus = normalizeMpesaStatus(statusResponse.status);
      setMpesaFlow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status: normalizedStatus,
          transactionId: statusResponse.transaction_id || prev.transactionId,
          checkoutRequestId: statusResponse.checkout_request_id || prev.checkoutRequestId,
          message: statusResponse.result_desc || prev.message,
        };
      });
    } catch (error) {
      console.error("Failed to refresh M-Pesa status", error);
    }
  }, [mpesaFlow?.requestName]);

  /** "Check with M-Pesa": ask Safaricom about a push whose confirmation has not arrived. */
  const checkWithMpesa = useCallback(async (requestName: string) => {
    setIsCheckingMpesa(true);
    try {
      const check = await checkMpesaPush(requestName);
      const message = pushCheckMessage(check);
      setMpesaFlow((prev) => {
        if (!prev || prev.requestName !== requestName) return prev;
        if (check.outcome === "paid") {
          return { ...prev, status: "completed", transactionId: check.transaction_id || prev.transactionId, message };
        }
        if (check.outcome === "not_paid") return { ...prev, status: "failed", message };
        return { ...prev, message };
      });
      if (check.outcome === "waiting" || check.outcome === "no_answer") toast.info(message);
    } catch (error) {
      toast.error(extractErrorFromException(error, "Couldn't check with M-Pesa"));
    } finally {
      setIsCheckingMpesa(false);
    }
  }, []);

  const selectedMpesaTotal = useMemo(
    () => selectedMpesaPayments.reduce((sum, payment) => sum + Number(payment.open_amount ?? payment.transamount ?? 0), 0),
    [selectedMpesaPayments]
  );

  // Cash the way ERPNext tells it when it books change: the Mode of Payment's type (the
  // rule utils/returnModes applies to refunds).
  const cashMethodIds = useMemo(
    () => new Set(cashRefundModes(modes).map((mode) => mode.mode_of_payment)),
    [modes]
  );
  // The real payment rows with vouchers applied: cash net of the change handed back, and
  // any overpay no cash row can absorb (utils/voucher netOfChange).
  const tenderNetOfChange = (vouchersTotal: number) =>
    netOfChange(
      Object.entries(paymentAmounts)
        .filter(([method, amount]) => method !== CUSTOMER_CREDIT_METHOD && amount > 0)
        .map(([method, amount]) => ({ method, amount })),
      vouchersTotal,
      checkoutPayableTotal,
      (method) => cashMethodIds.has(method),
      lastModifiedMethodId
    );

  const buildPaymentData = (
    deliveryPersonnel: string | null = null,
    options?: { excludeActiveMpesa?: boolean }
  ) => {
    const activeMpesaPayment = options?.excludeActiveMpesa ? getActiveMpesaPayment() : null;
    // Customer credit is not a payment row: it leaves this list, leaves amountPaid,
    // and reaches the server as customerCredit allocations settled after submit.
    // Draft and M-Pesa-order submits have no credit wiring server-side, so those
    // flows carry no credit at all - the tender is hidden and zeroed for them too.
    const creditFlowBlocked = Boolean(
      mpesaOrderName || mpesaDraftInvoiceName || getOriginalDraftInvoiceId()
    );
    const creditAmount = creditFlowBlocked
      ? 0
      : roundCurrency(paymentAmounts[CUSTOMER_CREDIT_METHOD] || 0);
    // With vouchers going to the server, cash goes net of the change handed back: ERPNext
    // books change only when paid exceeds the total, which a voucher sale never does.
    const tenderRows = tenderNetOfChange(creditAmount).rows.filter((row) => row.amount > 0);

    return {
      items: cartItems.map((item) => {
        const code = item.item_code || item.id;
        const discountData = itemDiscounts[code] || itemDiscounts[item.id] || {};
        return {
          ...item,
          id: item.item_code || item.id,
          item_code: item.item_code || item.id,
          price: getEffectiveItemRate(item),
          uom: item.uom || "Nos",
          discountPercentage: discountData.discountPercentage || 0,
          discountAmount: discountData.discountAmount || 0,
          serial_batch_bundle: discountData.serial_batch_bundle || null,
        };
      }),
      customer: selectedCustomer,
      paymentMethods: tenderRows.filter(({ method }) => {
        if (!activeMpesaPayment) return true;
        return method !== activeMpesaPayment.method;
      }).map(({ method, amount }) => {
        const paymentLine: Record<string, unknown> = {
          method,
          amount: parseFloat((Number(amount) || 0).toFixed(2)),
        };

        if (
          mpesaFlow &&
          mpesaFlow.source === "stk" &&
          mpesaFlow.modeOfPayment === method &&
          mpesaFlow.status === "completed" &&
          mpesaFlow.requestName
        ) {
          paymentLine.reference_no = mpesaFlow.transactionId || mpesaFlow.requestName;
          paymentLine.phone_number = mpesaFlow.phoneNumber;
          paymentLine.type = "Phone";
          paymentLine.custom_reference_text = mpesaFlow.requestName;
        }

        // Bank/Cheque manual reference — never overwrite the M-Pesa auto reference above.
        if (!paymentLine.reference_no && paymentReferences[method]) {
          paymentLine.reference_no = paymentReferences[method];
        }

        return paymentLine;
      }),
      subtotal: displaySubtotal,
      SalesTaxCharges: selectedSalesTaxCharges,
      taxAmount: displayTaxTotal,
      taxType: displayTaxIsIncluded ? "inclusive" : "exclusive",
      couponDiscount: calculations.couponDiscount,
      orderDiscountAmount: Number(orderDiscountAmount || 0),
      deliveryCharge: Number(deliveryCharge || 0),
      delivery_charge: Number(deliveryCharge || 0),
      remarks: remarks.trim(),
      shipping_rule: activeShippingRule || null,
      grandTotal: checkoutGrandTotal,
      amountPaid:
        creditAmount > 0
          ? calculateTotalPayments(tenderRows.map((row) => row.amount))
          : roundCurrency(Math.max(0, totalPaidAmount - creditAmount)),
      customerCredit: creditFlowBlocked
        ? []
        : appliedVouchers.map((voucher) => ({
            invoice: voucher.note,
            amount: voucher.amount,
            ...(voucher.original ? { original: voucher.original } : {}),
          })),
      outstandingAmount: outstandingAmount,
      appliedCoupons,
      businessType: posDetails?.business_type,
      deliveryPersonnel: deliveryPersonnel || null,
      isCreditSale,
      dueDate: isCreditSale ? dueDate : null,
      is_credit_sale: isCreditSale,
      due_date: isCreditSale ? dueDate : null,
      // The server works the due date out from the terms; dueDate above is what was shown.
      paymentTermsTemplate: usingTerms ? termsTemplate : null,
      allowPartialPayment: allowPartialPayments,
      allow_partial_payment: allowPartialPayments,
      salesperson: currentSalesperson?.name || null,
      tax_id: walkinDetails.taxId || null,
      walkin_name: walkinDetails.name || null,
      walkin_phone: walkinDetails.phone || null,
      extra_fields: extraFields,
      loyalty: appliedLoyalty
        ? {
            loyalty_program: appliedLoyalty.loyalty_program,
            loyalty_points: appliedLoyalty.loyalty_points,
          }
        : null,
    };
  };

  const ensureMpesaDraftInvoice = async () => {
    if (mpesaDraftInvoiceName) {
      return mpesaDraftInvoiceName;
    }

    const draftResponse = await createDraftSalesInvoice({
      ...buildPaymentData(selectedDeliveryPersonnel, { excludeActiveMpesa: true }),
      // No payment method is included yet (STK/reconcile payment is pending),
      // so mark this as "held" to bypass the "must have a positive payment
      // amount" cash-sale validation — same flag the hold-order flow uses.
      status: "held",
      enable_background_invoice_submission: false,
    });

    const draftName = draftResponse.invoice_name || draftResponse.invoice?.name;
    if (!draftName) {
      throw new Error("Draft invoice was created without a name");
    }

    setMpesaDraftInvoiceName(draftName);
    return draftName;
  };

  /**
   * The order the push is sent from: created on the first push, brought up to the cart on each
   * one after, so the order - and what the push asks for - is what the cashier is charging.
   * A kept M-Pesa order resumed from the Held tab is reused rather than copied.
   */
  const ensureMpesaOrder = async () => {
    const resumed = getOriginalHeldOrderMpesa().isMpesaOrder ? getOriginalHeldOrderId() : null;
    const name = await saveMpesaOrder(
      {
        ...buildPaymentData(selectedDeliveryPersonnel, { excludeActiveMpesa: true }),
        status: "held",
      },
      mpesaOrderName || resumed,
    );
    setMpesaOrderName(name);
    // From here a push may go out: leaving checkout hands the order back to the server.
    unfinishedMpesaOrderRef.current = name;
    return name;
  };

  /** Send an STK push; true once Safaricom accepted it. */
  const initiateMpesaFlow = async (method: string, amount: number, phoneNumber: string): Promise<boolean> => {
    if (!selectedCustomer || !selectedCustomer.name) {
      toast.error("Kindly select a customer");
      return false;
    }
    // Checked before ensureMpesaOrder: an M-Pesa order drops the vouchers, and the customer
    // would then owe what they covered on top of the push.
    const voucherReason = vouchersBlockMpesaReason(appliedVouchers.length);
    if (voucherReason) {
      toast.error(voucherReason);
      return false;
    }
    if (!phoneNumber.trim()) {
      toast.error("Phone number is required for M-Pesa STK push");
      return false;
    }
    if (!posCompanyName) {
      toast.error("POS company is missing. Unable to initiate M-Pesa STK push.");
      return false;
    }

    mpesaWorkInFlightRef.current += 1;
    try {
      setIsProcessingPayment(true);
      // A draft Sales Order, not an invoice: a push the customer never pays leaves no invoice.
      const orderName = await ensureMpesaOrder();

      const accountReference = orderName;
      const response = await initiateKlikPosStkPush({
        phone_number: phoneNumber,
        amount,
        mode_of_payment: method,
        company: posCompanyName,
        account_reference: accountReference,
        reference_doctype: "Sales Order",
        reference_name: orderName,
        currency: "KES",
        prevent_duplicates: 1,
      });

      setMpesaFlow({
        modeOfPayment: method,
        amount,
        phoneNumber: phoneNumber,
        accountReference,
        source: "stk",
        requestName: response.request_name,
        checkoutRequestId: response.checkout_request_id,
        transactionId: response.transaction_id,
        status: normalizeMpesaStatus(response.request_status),
        message: response.duplicate_prevented
          ? "Using existing pending M-Pesa request"
          : "STK push sent. Awaiting customer confirmation.",
      });
      toast.info("STK push sent. Awaiting customer confirmation.");
      return true;
    } catch (error) {
      if (error instanceof HeldOrderGoneError) {
        // Finished or cleared elsewhere. Not sent again by itself: it may have been paid.
        if (error.orderId === getOriginalHeldOrderId()) forgetOriginalHeldOrder();
        unfinishedMpesaOrderRef.current = null;
        setMpesaOrderName(null);
        setMpesaFlow(null);
        toast.warning(error.message, { autoClose: 10000 });
        return false;
      }
      toast.error(extractErrorFromException(error, "Failed to initiate M-Pesa STK push"));
      return false;
    } finally {
      mpesaWorkInFlightRef.current -= 1;
      setIsProcessingPayment(false);
    }
  };

  /** Bring the M-Pesa panel back into view (and reopen the mobile overlay). */
  const handleOpenMpesaOptions = () => {
    setMpesaPanelDismissed(false);
    mpesaOptionsPanelRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  const salespersonBlocksMpesa = () => {
    if (requiresSalespersonPin && !currentSalesperson) {
      setShowSalespersonModal(true);
      toast.error("Verify the salesperson before managing M-Pesa payments");
      return true;
    }
    return false;
  };

  const handleInitiateMpesaPayment = async () => {
    if (salespersonBlocksMpesa()) return;
    const activeMpesaPayment = getActiveMpesaPayment();
    if (!activeMpesaPayment || activeMpesaPayment.amount <= 0) {
      toast.error("Enter an amount on an M-Pesa payment method before initiating STK push.");
      return;
    }

    await initiateMpesaFlow(activeMpesaPayment.method, activeMpesaPayment.amount, mpesaPhoneNumber.trim());
    if (isMobile) setMpesaPanelDismissed(true);
  };

  // A paid push's receipt is pending: the panel lists its matches (or what a search finds), and
  // only one of them can be its receipt.
  const mpesaPanelPayments = receiptPending && mpesaSearchTerm.trim().length < 3 ? pushReceipts : mpesaRegisterPayments;

  const handleToggleMpesaPayment = (paymentName: string) => {
    const payment = mpesaPanelPayments.find((entry) => entry.name === paymentName);
    if (!payment) return;

    setSelectedMpesaPayments((prev) => {
      const exists = prev.some((entry) => entry.name === paymentName);
      if (exists) {
        return prev.filter((entry) => entry.name !== paymentName);
      }
      return receiptPending ? [payment] : [...prev, payment];
    });
  };

  /** "Use this receipt": the ticked receipt becomes the paid push's own; the sale then submits as usual. */
  const handleUsePushReceipt = async () => {
    const requestName = mpesaFlow?.requestName;
    const receipt = selectedMpesaPayments[0];
    if (!requestName || !receipt || selectedMpesaPayments.length !== 1) return;
    setIsProcessingPayment(true);
    try {
      const { transaction_id } = await attachPushReceipt(requestName, receipt.name);
      setMpesaFlow((prev) =>
        prev && prev.requestName === requestName
          ? { ...prev, transactionId: transaction_id, message: "Payment confirmed" }
          : prev,
      );
      setSelectedMpesaPayments([]);
      setPushReceipts([]);
      setMpesaSearchTerm("");
    } catch (error) {
      toast.error(extractErrorFromException(error, "Couldn't use this receipt"));
    } finally {
      setIsProcessingPayment(false);
    }
  };

  const handleReconcileMpesaPayments = async () => {
    if (salespersonBlocksMpesa()) return;
    if (stkLockedMethod) {
      // Receipts would replace the push's row and flow, orphaning money already asked for.
      toast.error("An M-Pesa push is pending or paid on this sale - receipts can't be added to it.");
      return;
    }
    const voucherReason = vouchersBlockMpesaReason(appliedVouchers.length);
    if (voucherReason) {
      toast.error(voucherReason);
      return;
    }
    if (!selectedCustomer?.id && !selectedCustomer?.name) {
      toast.error("Kindly select a customer");
      return;
    }

    const activeMpesaPayment = getActiveMpesaPayment();
    if (!activeMpesaPayment || activeMpesaPayment.amount <= 0) {
      toast.error("Enter an amount on an M-Pesa payment method before reconciling payments.");
      return;
    }

    if (!selectedMpesaPayments.length) {
      toast.error("Select at least one M-Pesa register payment to reconcile.");
      return;
    }

    mpesaWorkInFlightRef.current += 1;
    try {
      setIsProcessingPayment(true);
      const draftInvoiceName = await ensureMpesaDraftInvoice();
      await processKlikPosMpesaPayments({
        doctype: "Sales Invoice",
        invoice_name: draftInvoiceName,
        customer: selectedCustomer.id || selectedCustomer.name,
        mpesa_payments: selectedMpesaPayments.map((payment) => payment.name).join(","),
        mode_of_payment: activeMpesaPayment.method,
        auto_save: 1,
        auto_submit: 0,
      });

      // Receipts accumulate across picks; together they pay what the sale still owes after
      // the other methods, and whatever they hold beyond that stays on the receipts.
      const alreadyLinked =
        mpesaFlow?.source === "c2b" && mpesaFlow.draftInvoiceName === draftInvoiceName ? mpesaFlow.c2bPayments ?? [] : [];
      const linked = [
        ...alreadyLinked,
        ...selectedMpesaPayments.map((payment) => ({
          name: payment.name,
          amount: Number(payment.open_amount ?? payment.transamount ?? 0),
          transid: payment.transid,
        })),
      ];
      const linkedOpen = linked.reduce((sum, payment) => sum + payment.amount, 0);
      const owedByMpesa = roundCurrency(
        checkoutPayableTotal -
          calculateTotalPayments(
            Object.entries(paymentAmounts)
              .filter(([method]) => method !== activeMpesaPayment.method)
              .map(([, amount]) => amount),
          ),
      );
      const applied = appliedFromReceipts(linkedOpen, owedByMpesa);

      setPaymentAmounts((prev) => ({ ...prev, [activeMpesaPayment.method]: applied }));
      setMpesaFlow({
        modeOfPayment: activeMpesaPayment.method,
        amount: applied,
        phoneNumber: "",
        accountReference: draftInvoiceName,
        source: "c2b",
        draftInvoiceName,
        status: "completed",
        message: undefined,
        c2bPayments: linked,
      });
      if (isMobile) setMpesaPanelDismissed(true);
      setSelectedMpesaPayments([]);
      setMpesaSearchTerm("");
      toast.success("M-Pesa register payments added to draft invoice.");
    } catch (error) {
      toast.error(extractErrorFromException(error, "Failed to reconcile M-Pesa payments"));
    } finally {
      mpesaWorkInFlightRef.current -= 1;
      setIsProcessingPayment(false);
    }
  };

  const autoAllocateRemainingToNextMethod = (
    methodId: string,
    baseAmounts: PaymentAmount,
  ): PaymentAmount => {
    if (!autoAllocateRemainingPayment) {
      return baseAmounts;
    }

    const nextMethodIds = nextAllocationTargets(orderedPaymentMethodIds, methodId, stkLockedMethod);
    if (nextMethodIds.length === 0) {
      return baseAmounts;
    }

    const updatedAmounts: PaymentAmount = { ...baseAmounts };

    // Reset trailing payment modes so the remainder can be re-apportioned cleanly.
    nextMethodIds.forEach((id) => {
      updatedAmounts[id] = 0;
    });

    const remaining = roundCurrency(
      checkoutPayableTotal - calculateTotalPayments(Object.values(updatedAmounts)),
    );

    if (remaining > 0) {
      const nextMethodId = nextMethodIds[0];
      if (nextMethodId) {
        updatedAmounts[nextMethodId] = remaining;
      }
    }

    return updatedAmounts;
  };

  const handleToggleMethod = (methodId: string) => {
    if (invoiceSubmitted || isProcessingPayment) return;
    if (methodId === stkLockedMethod) return;
    const currentAmount = paymentAmounts[methodId] || 0;
    if (currentAmount > 0) {
      // turn off: clear this row's amount (reference is pruned by the effect in Step 2)
      setPaymentAmounts((amts) => ({ ...amts, [methodId]: 0 }));
    } else {
      // turn on: fill what is owed, or take over from a single row holding the whole sale
      const backedByMpesa =
        mpesaFlow && (mpesaFlow.source === "c2b" || mpesaFlow.status === "completed") ? [mpesaFlow.modeOfPayment] : [];
      // Applied vouchers are money already held: a toggle never empties their total.
      setPaymentAmounts((amts) => toggleOn(amts, methodId, checkoutPayableTotal, [...backedByMpesa, CUSTOMER_CREDIT_METHOD]));
      setLastModifiedMethodId(methodId);
      setActiveMethodId(methodId);
    }
  };

  const handleReferenceChange = (methodId: string, value: string) => {
    setPaymentReferences((refs) => ({ ...refs, [methodId]: value }));
  };

  const handleManualAmountChange = (methodId: string, amount: string) => {
    if (invoiceSubmitted || isProcessingPayment) return;
    if (methodId === stkLockedMethod) return;
    const numericAmount = roundCurrency(parseFloat(amount) || 0);
    setLastModifiedMethodId(methodId);
    setPaymentAmounts((prev) => {
      const baseAmounts = { ...prev, [methodId]: numericAmount };
      return autoAllocateRemainingToNextMethod(methodId, baseAmounts);
    });
  };

  // Keep references in sync with amounts: a method zeroed by any path (toggle-off,
  // auto-allocate re-apportioning, manual clear) drops its stored reference.
  useEffect(() => {
    setPaymentReferences((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        if ((paymentAmounts[key] || 0) <= 0) {
          delete next[key];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [paymentAmounts]);

  // The first preview can leave before the default tax template has loaded. When the
  // template lands it changes the payload, and that request is still part of opening
  // checkout - so it skips the debounce too. Declared before the preview effect so the flag
  // is set by the time that effect schedules its request in the same render.
  useEffect(() => {
    if (selectedSalesTaxCharges) taxPreviewImmediateRef.current = true;
  }, [selectedSalesTaxCharges]);

  useEffect(() => {
    const requestId = taxPreviewRequestIdRef.current + 1;
    taxPreviewRequestIdRef.current = requestId;

    const previewPayload = {
      customer: { id: selectedCustomer?.id },
      items: cartItems.map((item) => {
        const code = item.item_code || item.id;
        const discountData = itemDiscounts[code] || itemDiscounts[item.id] || {};
        const rawItemTaxRate = (item.item_tax_rate || {}) as Record<string, number>;
        const normalizedItemTaxRate: Record<string, number> = {};
        Object.keys(rawItemTaxRate)
          .sort()
          .forEach((key) => {
            normalizedItemTaxRate[key] = Number(rawItemTaxRate[key] || 0);
          });

        return {
          id: code,
          quantity: Number(item.quantity || 0),
          los_qty: Number(item.los_qty || 0),
          price: Number(getEffectiveItemRate(item) || 0),
          uom: item.uom || "Nos",
          discountPercentage: Number(discountData.discountPercentage || 0),
          discountAmount: Number(discountData.discountAmount || 0),
          bundle_entries: discountData.bundle_entries || [],
          description: item.description || "",
          item_tax_template: item.item_tax_template || "",
          item_tax_rate: normalizedItemTaxRate,
        };
      }),
      SalesTaxCharges: selectedSalesTaxCharges,
      businessType: posDetails?.business_type || "",
      deliveryCharge: Number(deliveryCharge || 0),
      shipping_rule: activeShippingRule || null,
      orderDiscountAmount: Number(orderDiscountAmount || 0),
      loyalty: appliedLoyalty
        ? {
            loyalty_program: appliedLoyalty.loyalty_program,
            loyalty_points: appliedLoyalty.loyalty_points,
          }
        : null,
    };

    const previewCacheKey = JSON.stringify(previewPayload);

    const fetchBackendTaxPreview = async () => {
      const step = taxPreviewStep({
        isOpen,
        invoiceSubmitted,
        hasCustomer: Boolean(selectedCustomer?.id),
        cartCount: cartItems.length,
      });
      if (step === "keep") return;
      if (step === "clear" || !selectedCustomer?.id) {
        setBackendTaxPreview(null);
        backendTaxPreviewRef.current = null;
        setTaxPreviewError(null);
        return;
      }

      if (salesTaxLoading) {
        return;
      }

      if (defaultTax && !selectedSalesTaxCharges) {
        return;
      }

      // Only spend the "no debounce" pass on a request that actually goes out, not on a
      // run that bailed while the tax templates were still loading.
      taxPreviewImmediateRef.current = false;

      const now = Date.now();
      const cachedEntry = taxPreviewCacheRef.current.get(previewCacheKey);
      if (cachedEntry && now - cachedEntry.timestamp <= TAX_PREVIEW_CACHE_TTL_MS) {
        setBackendTaxPreview(cachedEntry.taxPreview);
        backendTaxPreviewRef.current = cachedEntry.taxPreview;
        setTaxPreviewError(null);
        setIsTaxPreviewLoading(false);
        return;
      }

      setIsTaxPreviewLoading(true);
      try {
        const payload = {
          customer: { id: selectedCustomer.id },
          items: cartItems.map((item) => {
            const code = item.item_code || item.id;
            const discountData = itemDiscounts[code] || itemDiscounts[item.id] || {};
            return {
              id: code,
              quantity: item.quantity,
              los_qty: item.los_qty ?? 0,
              price: getEffectiveItemRate(item),
              uom: item.uom || "Nos",
              discountPercentage: discountData.discountPercentage || 0,
              discountAmount: discountData.discountAmount || 0,
              bundle_entries: discountData.bundle_entries || [],
              description: item.description || "",
              item_tax_template: item.item_tax_template || "",
              item_tax_rate: item.item_tax_rate || {},
            };
          }),
          itemDiscounts,
          SalesTaxCharges: selectedSalesTaxCharges,
          businessType: posDetails?.business_type,
          deliveryCharge,
          shipping_rule: activeShippingRule || null,
          orderDiscountAmount: Number(orderDiscountAmount || 0),
          loyalty: appliedLoyalty
            ? {
                loyalty_program: appliedLoyalty.loyalty_program,
                loyalty_points: appliedLoyalty.loyalty_points,
              }
            : null,
          // Preview-only context: avoid checkout payment validation until user submits payment.
          status: "held",
        };

        const inFlight = taxPreviewInFlightRef.current;
        let pending = inFlight.get(previewCacheKey);
        if (!pending) {
          const request = validateCheckoutInvoice(payload);
          inFlight.set(previewCacheKey, request);
          const settled = () => {
            if (inFlight.get(previewCacheKey) === request) inFlight.delete(previewCacheKey);
          };
          request.then(settled, settled);
          pending = request;
        }
        const response = await pending;
        if (response?.los_adjustments?.length) {
          void useCartStore.getState().applyCheckoutLosAdjustments(response.los_adjustments);
        }
        if (taxPreviewRequestIdRef.current === requestId) {
          if (response?.tax_preview) {
            setBackendTaxPreview(response.tax_preview);
            backendTaxPreviewRef.current = response.tax_preview;
            // A preview that split the cart describes the split cart, not this key's one;
            // cached, it would come back (pre-split) when the cart returns to this key.
            if (!response.los_adjustments?.length) {
              taxPreviewCacheRef.current.set(previewCacheKey, {
                taxPreview: response.tax_preview,
                timestamp: Date.now(),
              });
            }

            if (taxPreviewCacheRef.current.size > TAX_PREVIEW_CACHE_MAX_ENTRIES) {
              for (const [key, entry] of taxPreviewCacheRef.current.entries()) {
                if (Date.now() - entry.timestamp > TAX_PREVIEW_CACHE_TTL_MS) {
                  taxPreviewCacheRef.current.delete(key);
                }
              }
              while (taxPreviewCacheRef.current.size > TAX_PREVIEW_CACHE_MAX_ENTRIES) {
                const oldestKey = taxPreviewCacheRef.current.keys().next().value;
                if (!oldestKey) break;
                taxPreviewCacheRef.current.delete(oldestKey);
              }
            }
            setTaxPreviewError(null);
          } else {
            setTaxPreviewError(
              backendTaxPreviewRef.current
                ? "Preview refresh returned no tax details. Showing the last successful preview."
                : "Preview did not return tax details. Showing local estimate."
            );
          }
        }
      } catch (err) {
        if (taxPreviewRequestIdRef.current === requestId) {
          setTaxPreviewError(
            backendTaxPreviewRef.current
              ? extractErrorFromException(err, "Preview refresh failed. Showing the last successful preview.")
              : extractErrorFromException(err, "Preview request failed. Showing local estimate.")
          );
          console.error("Failed to fetch backend tax preview:", err);
        }
      } finally {
        if (taxPreviewRequestIdRef.current === requestId) {
          setIsTaxPreviewLoading(false);
        }
      }
    };

    const timeoutId = window.setTimeout(() => {
      fetchBackendTaxPreview();
    }, taxPreviewImmediateRef.current || taxPreviewInFlightRef.current.has(previewCacheKey) ? 0 : TAX_PREVIEW_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [
    isOpen,
    invoiceSubmitted,
    selectedCustomer?.id,
    cartItems,
    itemDiscounts,
    selectedSalesTaxCharges,
    defaultTax,
    salesTaxLoading,
    posDetails?.business_type,
    deliveryCharge,
    activeShippingRule,
    orderDiscountAmount,
    appliedLoyalty,
    isCreditSale,
    dueDate,
    allowPartialPayments,
    getEffectiveItemRate,
  ]);

  const mpesaCustomer = selectedCustomer?.id || selectedCustomer?.name || undefined;

  useEffect(() => {
    if (!showMpesaPanel || !posCompanyName || !activeMpesaMethod) return;

    let cancelled = false;
    const loadMpesaRegisterPayments = async () => {
      setIsLoadingMpesaRegisterPayments(true);
      try {
        const response = await fetchMpesaRegisterPayments({
          company: posCompanyName,
          pos_profile: posProfileName || undefined,
          mode_of_payment: activeMpesaMethod,
          search: mpesaSearchTerm.trim().length >= 3 ? mpesaSearchTerm.trim() : undefined,
          customer: mpesaCustomer,
        });
        if (cancelled) return;
        setMpesaRegisterCount(Number(response.count || 0));
        setMpesaRegisterPayments(response.payments || []);
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load M-Pesa register payments", error);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingMpesaRegisterPayments(false);
        }
      }
    };

    void loadMpesaRegisterPayments();
    return () => {
      cancelled = true;
    };
  }, [showMpesaPanel, posCompanyName, posProfileName, mpesaSearchTerm, activeMpesaMethod, mpesaCustomer]);

  useEffect(() => {
    if (!showMpesaPanel) return;
    // The customer's own number, or the walk-in's when the cashier took one.
    setMpesaPhoneNumber((current) => current || selectedCustomer?.phone || walkinDetails?.phone || "");
    mpesaOptionsPanelRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    // Only when the panel appears, not on every customer edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMpesaPanel]);

  useEffect(() => {
    if (mpesaFlow?.source !== "stk" || !mpesaFlow?.requestName) return;
    if (mpesaFlow.status === "completed" || mpesaFlow.status === "failed") return;

    const interval = window.setInterval(() => {
      void refreshMpesaStatus(mpesaFlow.requestName);
    }, 5000);

    return () => {
      window.clearInterval(interval);
    };
  }, [mpesaFlow?.requestName, mpesaFlow?.source, mpesaFlow?.status, refreshMpesaStatus]);

  // Safaricom's confirmation can be lost: a minute into the wait the till asks once by itself,
  // and from then on offers "Check with M-Pesa".
  const autoCheckRequest = autoCheckFor(mpesaFlow, checkOfferedFor);
  useEffect(() => {
    if (!autoCheckRequest) return;
    const timer = window.setTimeout(() => {
      setCheckOfferedFor(autoCheckRequest);
      void checkWithMpesa(autoCheckRequest);
    }, AUTO_CHECK_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [autoCheckRequest, checkWithMpesa]);

  // A paid push without its receipt number: look for the receipt every 5 s - asking for a pull at
  // once and again at 30 s and 90 s - until one turns up, or give up after two minutes.
  const receiptLookupRequest =
    receiptPending && mpesaFlow?.requestName !== receiptLookupEndedFor ? mpesaFlow?.requestName : undefined;
  useEffect(() => {
    if (!receiptLookupRequest) return;
    const requestName = receiptLookupRequest;
    const startedAt = Date.now();
    let pulls = 0;
    let timer = 0;
    let cancelled = false;
    const look = async () => {
      const step = receiptLookupStep(Date.now() - startedAt, pulls);
      if (step.pull) pulls += 1;
      try {
        const found = await findPushReceipts(requestName, step.pull);
        if (cancelled) return;
        if (found.transaction_id) {
          // Safaricom's own confirmation arrived meanwhile: an ordinary paid push now.
          const transactionId = found.transaction_id;
          setMpesaFlow((prev) =>
            prev && prev.requestName === requestName ? { ...prev, transactionId, message: "Payment confirmed" } : prev,
          );
          return;
        }
        if (found.receipts.length > 0) {
          setPushReceipts(found.receipts);
          const only = pretickedReceipt(found.receipts);
          setSelectedMpesaPayments(only ? [only] : []);
          setMpesaPanelDismissed(false);
          setReceiptLookupEndedFor(requestName);
          return;
        }
      } catch (error) {
        console.error("Failed to look for the M-Pesa receipt", error);
      }
      if (cancelled) return;
      if (step.giveUp) {
        setReceiptLookupEndedFor(requestName);
        toast.warning(RECEIPT_GIVE_UP_MESSAGE, { autoClose: 15000, toastId: `stk-receipt-${requestName}` });
        return;
      }
      timer = window.setTimeout(() => void look(), RECEIPT_POLL_MS);
    };
    void look();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [receiptLookupRequest]);

  useEffect(() => {
    if (mpesaFlow?.source !== "stk" || !mpesaFlow?.requestName) return;
    const realtime = (window as typeof window & { frappe?: { realtime?: FrappeRealtimeClient } })?.frappe?.realtime;
    if (!realtime?.on) return;

    const handler = (data: MpesaRealtimeEvent) => {
      if (!data || data.request_name !== mpesaFlow.requestName) return;
      const status = normalizeMpesaStatus(data.status);
      setMpesaFlow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status,
          transactionId: data.transaction_id || prev.transactionId,
          message: status === "completed" && data.transaction_id ? "Payment confirmed" : prev.message,
        };
      });
      // A status check reports "paid" without the receipt number: the receipt lookup takes over.
      if (status === "completed" && data.transaction_id) {
        toast.success("M-Pesa payment confirmed.");
      }
    };

    realtime.on("mpesa_stk_payment_completed", handler);
    return () => {
      realtime.off?.("mpesa_stk_payment_completed", handler);
    };
  }, [mpesaFlow?.requestName, mpesaFlow?.source]);

  useEffect(() => {
    if (!isOpen) {
      // Closed (Hold included) with the M-Pesa sale unfinished.
      releaseUnfinishedMpesaDraft();
      setMpesaFlow(null);
      setMpesaDraftInvoiceName(null);
      setMpesaOrderName(null);
      setAlreadySubmittedAs(null);
      setMpesaPanelDismissed(false);
      setMpesaSearchTerm("");
      setSelectedMpesaPayments([]);
      // Resumed again later, the push is checked and its receipt looked for afresh.
      setCheckOfferedFor(null);
      setPushReceipts([]);
      setReceiptLookupEndedFor(null);
      setDeliveryCharge(0);
      // The next sale's customer brings their own number; never push to the last one's.
      setMpesaPhoneNumber("");
    }
  }, [isOpen, releaseUnfinishedMpesaDraft]);

  // Checkout resumed from an M-Pesa order kept for its push picks that push up: a paid one is
  // submitted, a pending one is waited on - neither is charged again.
  const resumedMpesaOrderRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isOpen) {
      resumedMpesaOrderRef.current = null;
      return;
    }
    const orderId = getOriginalHeldOrderId();
    const { isMpesaOrder, request } = getOriginalHeldOrderMpesa();
    if (!orderId || !isMpesaOrder || resumedMpesaOrderRef.current === orderId) return;
    const mpesaModes = modes
      .filter((mode) => isMpesaPaymentMode(mode, mode.mode_of_payment || ""))
      .map((mode) => mode.mode_of_payment)
      .filter((name): name is string => Boolean(name));
    if (!mpesaModes.length) return; // the till's modes are still loading
    resumedMpesaOrderRef.current = orderId;
    setMpesaOrderName(orderId);
    const flow = resumedMpesaFlow(orderId, request, mpesaModes);
    if (!flow) return;
    setMpesaFlow(flow);
    setMpesaPhoneNumber((current) => current || flow.phoneNumber);
  }, [isOpen, modes]);

  // A resumed order's push paid - when it was picked up, or while checkout waited on it: the
  // sale takes exactly what the customer paid, on the mode it came through. Without it the
  // till's opening amount (all on cash, say) would stand and the M-Pesa money go unrecorded.
  useEffect(() => {
    if (!mpesaFlow || mpesaFlow.source !== "stk" || mpesaFlow.status !== "completed") return;
    if (!mpesaOrderName || resumedMpesaOrderRef.current !== mpesaOrderName) return;
    const { modeOfPayment, amount } = mpesaFlow;
    if (!modeOfPayment || amount <= 0) return;
    setLastModifiedMethodId(modeOfPayment);
    setPaymentAmounts((prev) => withPaidMpesa(prev, modeOfPayment, amount, checkoutPayableTotal));
  }, [mpesaFlow, mpesaOrderName, checkoutPayableTotal]);

  useEffect(() => {
    clearLoyaltyRedemption();
  }, [clearLoyaltyRedemption, selectedCustomer?.id, isOpen]);

  const processPayment = async (deliveryPersonnel: string | null = null) => {
    if (!selectedCustomer || !selectedCustomer.name) {
      toast.error("Kindly select a customer");
      return;
    }
    if (hasNegativePaymentAmount) {
      toast.error("Payment amounts cannot be negative.");
      return;
    }
    if (!isCreditSale) {
      const totalPaid = calculateTotalPayments(Object.values(paymentAmounts));
      const orderTotal = checkoutPayableTotal;
      
      if (totalPaid < orderTotal) {
        const remainingAmount = orderTotal - totalPaid;
        toast.error(`Insufficient payment. Total: ${formatCurrencyWithSymbol(orderTotal, displayCurrencySymbol)}, Paid: ${formatCurrencyWithSymbol(totalPaid, displayCurrencySymbol)}, Remaining: ${formatCurrencyWithSymbol(remainingAmount, displayCurrencySymbol)}`);
        return;
      }
      
    }
    if (isCreditSale && !dueDate) {
      toast.error("Please select a due date for this credit sale");
      return;
    }
    if (isCreditSale && creditTermsLoading) {
      toast.info("Loading the customer's payment terms");
      return;
    }
    if (isB2C && !isCreditSale) {
      const activePaymentMethods = Object.entries(paymentAmounts).filter(([, amount]) => amount > 0);
      if (activePaymentMethods.length === 0) {
        toast.error("Please enter payment amounts");
        return;
      }
      if (outstandingAmount > 0) {
        toast.error("Please complete the payment before proceeding");
        return;
      }
    }
    setIsProcessingPayment(true);
    mpesaWorkInFlightRef.current += 1;
    const paymentData = buildPaymentData(deliveryPersonnel);
    const originalHeldOrderId = getOriginalHeldOrderId();
    const originalDraftInvoiceId = getOriginalDraftInvoiceId();
    let activeCheckoutRequestId: string | null = null;
    try {
      let response;

      if (mpesaOrderName && mpesaFlow?.source === "stk") {
        // The order the push went out from becomes the invoice; a held order the cart came
        // from (when it is not that order itself) is finished with it.
        response = await submitMpesaOrder(
          mpesaOrderName,
          { ...paymentData, enable_background_invoice_submission: enableBackgroundSubmission },
          originalHeldOrderId,
          remarks.trim(),
        );
        unfinishedMpesaOrderRef.current = null;
      } else if (mpesaDraftInvoiceName) {
        // Receipt-paid M-Pesa reaches the draft as advances, so its row stays out of the
        // payments; everything else the cashier took (cash added after the pick) goes in.
        const receiptData =
          mpesaFlow?.source === "c2b"
            ? receiptDraftSubmitData(buildPaymentData(deliveryPersonnel, { excludeActiveMpesa: true }))
            : paymentData;
        // A held order paid by M-Pesa: the server finishes the order with the draft.
        response = await submitDraftInvoice(
          mpesaDraftInvoiceName,
          receiptData && { ...receiptData, enable_background_invoice_submission: enableBackgroundSubmission },
          originalHeldOrderId,
          remarks.trim(),
        );
      } else if (originalHeldOrderId) {
        // Checkout from a held Sales Order — convert it to a submitted Sales Invoice
        const checkoutPayload = {
          ...paymentData,
          enable_background_invoice_submission: enableBackgroundSubmission,
        };
        const attempt = getOrCreateCheckoutAttempt(
          getCheckoutCartFingerprint(
            selectedCustomer?.id,
            cartItems as unknown as Array<Record<string, unknown>>,
          ),
          { heldOrder: originalHeldOrderId, ...checkoutPayload },
        );
        activeCheckoutRequestId = attempt.requestId;
        response = await checkoutHeldOrder(originalHeldOrderId, {
          ...checkoutPayload,
          checkout_request_id: attempt.requestId,
        });
        markCheckoutAttemptAccepted(attempt.requestId, response.invoice_name || response.invoice_id);
      } else if (originalDraftInvoiceId) {
        // Legacy path: editing a held draft Sales Invoice
        response = await submitDraftInvoice(
          originalDraftInvoiceId,
          {
            ...paymentData,
            enable_background_invoice_submission: enableBackgroundSubmission,
          }
        );
      } else {
        const checkoutPayload = {
          ...paymentData,
          enable_background_invoice_submission: enableBackgroundSubmission,
        };
        const attempt = getOrCreateCheckoutAttempt(
          getCheckoutCartFingerprint(
            selectedCustomer?.id,
            cartItems as unknown as Array<Record<string, unknown>>,
          ),
          checkoutPayload,
        );
        activeCheckoutRequestId = attempt.requestId;
        response = await createSalesInvoice({
          ...checkoutPayload,
          checkout_request_id: attempt.requestId,
        });
        markCheckoutAttemptAccepted(attempt.requestId, response.invoice_name || response.invoice_id);
      }

      const queued = checkoutWasQueued(response);
      setInvoiceSubmitted(true);
      setSubmissionQueued(queued);
      setSubmittedInvoice(response);
      setInvoiceData(response.invoice);
      setMpesaFlow(null);
      setMpesaDraftInvoiceName(null);
      setMpesaOrderName(null);
      toast.success(queued ? "Invoice queued for background submission!" : "Invoice submitted successfully!");

      // Follow a queued sale until it posts, so a failure is told now, not after a reload.
      // Inside Desk the realtime event already does this.
      const queuedRequestId = response?.checkout_request_id || activeCheckoutRequestId;
      const hasRealtime = Boolean((window as typeof window & { frappe?: { realtime?: unknown } }).frappe?.realtime);
      if (queued && queuedRequestId && !hasRealtime) {
        void watchQueuedCheckout(queuedRequestId, getCheckoutRequestStatus).then((failure) => {
          if (failure) window.dispatchEvent(new CustomEvent(QUEUE_FAILURE_EVENT, { detail: failure }));
        });
      }

      // A stale credit allocation never undoes the sale; the server says so here.
      const creditWarning = response?.customer_credit?.warning;
      if (creditWarning) {
        toast.warning(String(creditWarning), { autoClose: 10000 });
      }

      // What the receipts held beyond this sale stays on them for the customer's next
      // sale - never handed back as cash change. Surface it explicitly.
      const mpesaExcess = (response?.mpesa_reconciliation || []).reduce(
        (sum: number, r: any) => sum + Number(r?.excess_amount || 0),
        0
      );
      if (mpesaExcess > 0) {
        const who = selectedCustomer?.customerName || selectedCustomer?.name || "the customer";
        toast.success(receiptLeftoverMessage(mpesaExcess, displayCurrencySymbol, who), { autoClose: 8000 });
      }

      clearDraftInvoiceCache();
    } catch (err: any) {
      if (err instanceof DraftNoLongerDraftError) {
        // Submitted or cancelled elsewhere (e.g. from the desk); retrying can never succeed.
        const wasMpesaDraft = err.invoiceId === mpesaDraftInvoiceName;
        const notice = staleDraftNotice(err.invoiceId, err.docstatus, { wasMpesaDraft });
        if (notice.blockSubmit) {
          // Already recorded: keep the link and block Submit rather than ring it up twice.
          setAlreadySubmittedAs(err.invoiceId);
        } else {
          if (wasMpesaDraft) {
            // The M-Pesa receipt was attached to the cancelled draft. Clear the amount so it
            // is not recorded again as a bare payment row with no receipt behind it.
            const activeMpesa = getActiveMpesaPayment();
            if (activeMpesa) {
              setPaymentAmounts((prev) => ({ ...prev, [activeMpesa.method]: 0 }));
            }
            setSelectedMpesaPayments([]);
            setMpesaDraftInvoiceName(null);
            setMpesaFlow(null);
          }
          if (err.invoiceId === getOriginalDraftInvoiceId()) {
            forgetOriginalDraftInvoice();
          }
        }
        toast[notice.level](notice.message, { autoClose: 10000, toastId: `stale-draft-${err.invoiceId}` });
        return;
      }
      if (err instanceof HeldOrderGoneError) {
        if (err.orderId === mpesaOrderName) {
          // Finished or cleared elsewhere: its push went with it. Start M-Pesa afresh.
          unfinishedMpesaOrderRef.current = null;
          setMpesaOrderName(null);
          setMpesaFlow(null);
        }
        // The server ruled out a replay of this checkout first, so nothing was created
        // under this attempt; start the next Submit on a fresh one.
        if (activeCheckoutRequestId) clearCheckoutAttempt(activeCheckoutRequestId);
        forgetOriginalHeldOrder();
        toast.warning(heldOrderGoneMessage(err.message, "checkout"), {
          autoClose: 10000,
          toastId: `held-gone-${err.orderId}`,
        });
        return;
      }
      if (activeCheckoutRequestId) {
        // The checkout failed, but an invoice may still exist on the server. Keep the key
        // when it does, so a retry replays instead of ringing the sale up twice; drop it
        // when nothing was created, so the cashier gets a clean attempt.
        const existingInvoice = err?.checkoutResponse?.invoice_name || err?.checkoutResponse?.invoice_id;
        if (existingInvoice) {
          markCheckoutAttemptAccepted(activeCheckoutRequestId, existingInvoice);
        } else if (err?.checkoutResponseReceived) {
          clearCheckoutAttempt(activeCheckoutRequestId);
        }
        // No response at all (network drop, timeout): keep the key. The recovery poll in
        // OrderSummary is the only thing that can tell whether an invoice landed.
      }
      const defaultMessage = isB2B ? "Failed to submit invoice" : "Failed to process payment";
      const errorMessage = extractErrorFromException(err, defaultMessage);
      toast.error(errorMessage);
    } finally {
      mpesaWorkInFlightRef.current -= 1;
      setIsProcessingPayment(false);
    }
  };

  // One submit at a time across the button, F10 and the paid-push auto-submit: a state flag
  // only lands on the next render, so two triggers in the same tick would both pass it.
  const submitInFlightRef = useRef(false);

  const handleCompletePayment = async () => {
    if (submitInFlightRef.current) return;
    submitInFlightRef.current = true;
    try {
      if (requiresSalespersonPin && !currentSalesperson) {
        setShowSalespersonModal(true);
        toast.error("Verify the salesperson before completing payment");
        return;
      }

      const activeMpesaPayment = getActiveMpesaPayment();
      if (activeMpesaPayment && activeMpesaPayment.amount > 0) {
        const sameRequestForMethod =
          mpesaFlow && mpesaFlow.modeOfPayment === activeMpesaPayment.method ? mpesaFlow : null;

        if (sameRequestForMethod?.source === "stk" && sameRequestForMethod.status === "in_progress") {
          toast.info("M-Pesa payment is still pending. Confirm on phone or click Refresh Status.");
          return;
        }

        if (sameRequestForMethod?.source === "stk" && sameRequestForMethod.status !== "completed" && sameRequestForMethod.requestName) {
          await refreshMpesaStatus(sameRequestForMethod.requestName);
          return;
        }
      }

      await processPayment(selectedDeliveryPersonnel);
    } finally {
      submitInFlightRef.current = false;
    }
  };

  const handleHoldOrder = async () => {
    if (!selectedCustomer) {
      toast.error("Kindly select a customer");
      return;
    }
    if (requiresSalespersonPin && !currentSalesperson) {
      setShowSalespersonModal(true);
      toast.error("Verify the salesperson before holding this order");
      return;
    }
    const mpesaHoldBlock = holdBlockedByMpesa(mpesaFlow);
    if (mpesaHoldBlock) {
      toast.error(mpesaHoldBlock);
      return;
    }

    setIsHoldingOrder(true);

    try {
      const orderItems = cartItems.map((item) => {
        const code = item.item_code || item.id;
        const discountData = itemDiscounts[code] || itemDiscounts[item.id] || {};
        const discountPercentage =
          Number(discountData.discountPercentage)
          || Number((item as { discount_percentage?: number }).discount_percentage)
          || 0;
        const discountAmount =
          Number(discountData.discountAmount)
          || Number((item as { discount_amount?: number }).discount_amount)
          || 0;

        let heldPrice = Number((item as { discountedPriceExcl?: number }).discountedPriceExcl);
        if (!Number.isFinite(heldPrice)) {
          heldPrice = getEffectiveItemRate(item);
        }

        return {
          ...item,
          price: heldPrice,
          item_code: code,
          discountPercentage,
          discountAmount,
        };
      });

      const totalItemDiscount = orderItems.reduce((sum, item) => {
        const basePrice =
          Number((item as { originalPrice?: number }).originalPrice)
          || Number((item as { original_price?: number }).original_price)
          || Number(item.price)
          || 0;
        const currentPrice = Number(item.price) || 0;
        return sum + Math.max(0, (basePrice - currentPrice) * item.quantity);
      }, 0);

      const orderData = {
        items: orderItems,
        customer: { id: selectedCustomer.id },
        customerData: selectedCustomer,
        subtotal: calculations.subtotal,
        total: checkoutGrandTotal,
        taxAmount: calculations.taxAmount,
        taxType: calculations.isInclusive ? "inclusive" : "exclusive",
        couponDiscount: calculations.couponDiscount,
        grandTotal: checkoutGrandTotal,
        appliedCoupons,
        itemDiscounts,
        totalItemDiscount,
        totalSavings: totalItemDiscount + calculations.couponDiscount,
        status: "held",
        businessType: posDetails?.business_type,
        salesperson: currentSalesperson?.name || null,
        // Buyer, extra fields, shipping rule, delivery, discount and tax template - built the
        // same way as the cart's Hold, from what checkout shows now.
        ...heldOrderPayloadExtras({
          walkin: walkinDetails,
          extraFields,
          shippingRule: activeShippingRule,
          extras: {
            deliveryCharge,
            deliveryPersonnel: selectedDeliveryPersonnel,
            orderDiscountAmount: Number(orderDiscountAmount || 0),
            salesTaxCharges: selectedSalesTaxCharges,
            remarks,
          },
          flags: tillFlags(posDetails as Record<string, unknown>),
        }),
        loyalty: appliedLoyalty
          ? {
              loyalty_program: appliedLoyalty.loyalty_program,
              loyalty_points: appliedLoyalty.loyalty_points,
            }
          : null,
        // The M-Pesa order (its push failed) becomes the held order, rather than a copy.
        held_order_id: getOriginalHeldOrderId() || mpesaOrderName,
      };

      const result = await createHeldOrder(orderData);
      if (!result?.success) {
        throw new Error("Failed to hold order");
      }
      if (result.order_name && result.order_name === mpesaOrderName) {
        // It is an ordinary held order now; closing checkout must not discard it.
        unfinishedMpesaOrderRef.current = null;
        setMpesaOrderName(null);
      }

      clearCart();
      if (result.approval_requested) {
        toast.success("Held and sent for price approval");
      } else {
        toast.success(orderData.held_order_id ? "Order updated and held successfully!" : "Order held successfully!");
      }
      await Promise.resolve(onHoldOrder(orderData));
    } catch (err: any) {
      if (err instanceof HeldOrderGoneError) {
        forgetOriginalHeldOrder();
        toast.warning(heldOrderGoneMessage(err.message, "hold"), { toastId: `held-gone-${err.orderId}` });
        return;
      }
      const errorMessage = extractErrorFromException(err, "Failed to hold order");
      toast.error(errorMessage);
    } finally {
      setIsHoldingOrder(false);
    }
  };

  const handleEditOrder = () => {
    closeDialog(false);
  };

  const handleViewInvoice = (invoice: any) => {
    void finalizeCompletedOrderState(() => {
      navigate(`/invoice/${invoice.name}`);
    });
  };

  const clearOrderState = () => {
    clearDraftInvoiceCache();
    clearCart();
  };

  const finalizeCompletedOrderState = async (afterClear?: () => void) => {
    if (invoiceSubmitted && !rememberSalesperson) {
      try {
        await clearActiveSalesperson(true);
      } catch (salespersonClearError) {
        console.error("Failed to clear salesperson session after completion:", salespersonClearError);
      }
    }

    clearOrderState();
    afterClear?.();
  };

  const getActionButtonText = () => {
    if (isProcessingPayment) return isB2B ? "Submitting Invoice..." : "Processing Payment...";
    if (mpesaFlow?.source === "stk" && mpesaFlow?.status === "completed") return "Submit Confirmed Payment";
    return "Submit";
  };

  const getMpesaButtonText = () => {
    if (isProcessingPayment) return "Processing M-Pesa...";
    if (mpesaFlow?.source === "stk" && mpesaFlow?.status === "in_progress") return "M-Pesa Pending";
    if (mpesaFlow?.source === "c2b") return "Review M-Pesa Options";
    return "M-Pesa Options";
  };


  const isMpesaButtonDisabled = () => {
    if (!hasActiveMpesaPayment) return true;
    if (invoiceSubmitted || isProcessingPayment) return true;
    if (!reconciliation.ok) return true;
    return false;
  };

  const mpesaReceiptsOpen =
    mpesaFlow?.source === "c2b" ? (mpesaFlow.c2bPayments ?? []).reduce((sum, payment) => sum + payment.amount, 0) : 0;
  const mpesaStkDone = mpesaFlow?.source === "stk" && mpesaFlow.status === "completed" && mpesaFlow.transactionId ? Number(mpesaFlow.amount || 0) : 0;
  const mpesaUncovered = uncoveredMpesa(getActiveMpesaPayment()?.amount || 0, mpesaReceiptsOpen, mpesaStkDone);

  // An overpay with vouchers applied that no cash row can take as change would be booked
  // as paid: the cashier reduces the non-cash row instead.
  const voucherOverpay = tenderNetOfChange(
    vouchersBlocked ? 0 : roundCurrency(paymentAmounts[CUSTOMER_CREDIT_METHOD] || 0)
  ).unabsorbed;

  const submitBlockReason = () => {
    const originalHeldOrderId = getOriginalHeldOrderId();
    const heldOrderApproval = originalHeldOrderId ? getOriginalHeldOrderApproval() : null;
    return paymentBlockReason({
      invoiceSubmitted,
      isProcessingPayment,
      reconciliationOk: reconciliation.ok,
      reconciliationMessage: reconciliation.message,
      isCreditSale,
      hasDueDate: Boolean(dueDate),
      creditTermsLoading,
      isB2C,
      outstandingAmount,
      outstandingLabel: formatCurrencyWithSymbol(outstandingAmount, displayCurrencySymbol),
      alreadySubmittedAs,
      priceApprovalMessage: heldOrderApproval
        ? priceApprovalMessage(heldOrderApproval.state, heldOrderApproval.priceBreach)
        : null,
      mpesaUncoveredLabel: mpesaUncovered > 0 ? formatCurrencyWithSymbol(mpesaUncovered, displayCurrencySymbol) : null,
      overpaidNonCashLabel: voucherOverpay > 0 ? formatCurrencyWithSymbol(voucherOverpay, displayCurrencySymbol) : null,
    });
  };

  const isActionButtonDisabled = () => submitBlockReason() !== null;
  // A non-cash overpay greys Submit while Change Due still reads green: say why by the button.
  const submitHint = !invoiceSubmitted && voucherOverpay > 0 ? submitBlockReason() : null;

  // A paid STK push submits the sale by itself - once per push request, and only when the
  // push alone settles the server's total (see stkAutoSubmitDecision).
  const [stkAutoSubmitFor, setStkAutoSubmitFor] = useState<string | null>(null);
  const handledStkRequestRef = useRef<string | null>(null);
  const previewReady = hasBackendTaxPreview && !isTaxPreviewLoading;

  useEffect(() => {
    if (!isOpen || invoiceSubmitted) return;
    if (mpesaFlow?.source !== "stk" || mpesaFlow.status !== "completed" || !mpesaFlow.requestName) return;
    // Paid with its receipt pending cannot submit - the server needs the receipt number. It is
    // decided once the receipt is attached, like any confirmed push.
    if (!mpesaFlow.transactionId) return;
    if (handledStkRequestRef.current === mpesaFlow.requestName) return;
    handledStkRequestRef.current = mpesaFlow.requestName;
    // The row shows what the customer actually paid, whatever it held before (a resumed
    // order's pre-filled total, say); the lock then keeps it there.
    const { modeOfPayment, amount } = mpesaFlow;
    if (modeOfPayment && amount > 0) {
      setPaymentAmounts((prev) => ({ ...prev, [modeOfPayment]: roundCurrency(amount) }));
    }
    setStkAutoSubmitFor(mpesaFlow.requestName);
  }, [isOpen, invoiceSubmitted, mpesaFlow]);

  useEffect(() => {
    if (!stkAutoSubmitFor || !mpesaFlow) return;
    const paidAmount = Number(mpesaFlow.amount || 0);
    const decision = stkAutoSubmitDecision({
      blockReason: submitBlockReason(),
      isProcessing: isProcessingPayment,
      invoiceSubmitted,
      previewReady,
      paidAmount,
      payable: checkoutPayableTotal,
      otherRowsTendered: Object.entries(paymentAmounts).some(
        ([methodId, value]) => methodId !== mpesaFlow.modeOfPayment && (value || 0) > 0
      ),
    });
    // Waiting keeps the request pending: this runs again when the server total lands.
    if (decision.action === "wait") return;
    const requestName = stkAutoSubmitFor;
    setStkAutoSubmitFor(null);
    if (decision.action === "submit") {
      void handleCompletePayment();
      return;
    }
    if (decision.action !== "notify") return;
    const paid = formatCurrencyWithSymbol(paidAmount, displayCurrencySymbol);
    const message =
      decision.reason === "blocked"
        ? `M-Pesa payment of ${paid} received. ${decision.detail} - then submit the sale.`
        : decision.reason === "short"
          ? `M-Pesa payment of ${paid} received - ${formatCurrencyWithSymbol(
              roundCurrency(checkoutPayableTotal - paidAmount),
              displayCurrencySymbol
            )} still to be paid. Collect it, then submit the sale.`
          : `M-Pesa payment of ${paid} received. Check the other payment rows, then submit the sale.`;
    toast.info(message, { autoClose: 10000, toastId: `stk-paid-${requestName}` });
    // Decided once per push, when the server total is in - never again on later edits,
    // which would submit while the cashier is still typing an amount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stkAutoSubmitFor, previewReady]);

  // isProcessingPayment only lands on the next render, so two quick F10 presses would
  // both see it false. The ref closes that gap for the shortcut.
  const f10SubmitInFlight = useRef(false);

  // While open, the dialog owns F10: the cart's Checkout underneath must not fire too.
  usePosShortcutLayer(
    {
      f10: () => {
        // The completed screen has nothing to submit.
        if (invoiceSubmitted || f10SubmitInFlight.current) return;
        const reason = submitBlockReason();
        if (reason) {
          toast.info(reason, { toastId: "pos-f10-blocked" });
          return;
        }
        f10SubmitInFlight.current = true;
        void handleCompletePayment().finally(() => {
          f10SubmitInFlight.current = false;
        });
      },
      // Shift+F10 holds, the keyboard twin of the Hold button.
      shiftF10: () => {
        if (allow_holding_invoices && !invoiceSubmitted && !isProcessingPayment && !isHoldingOrder) {
          void handleHoldOrder();
        }
      },
    },
    isOpen,
  );

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        // Leaving mid-payment would abandon an STK push or a submit still running.
        if (isProcessingPayment || isHoldingOrder) return;
        // The leave confirmation handles its own Escape (= stay); don't reopen it.
        if (leaveConfirmOpen) return;
        // Completed screen: ESC does the default "Start New Order" action.
        // Payment-entry screen: ESC closes the dialog.
        if (invoiceSubmitted) {
          void finalizeCompletedOrderState(() => onClose(true));
        } else {
          closeDialog(false);
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, invoiceSubmitted, isProcessingPayment, isHoldingOrder, finalizeCompletedOrderState, onClose, closeDialog, leaveConfirmOpen]);

  const buildOrderText = () => {
    const lines: string[] = [];
    if (invoiceSubmitted && invoiceData?.name) {
      lines.push(`Invoice: ${invoiceData.name}`);
      if (invoiceData.posting_date) lines.push(`Date: ${invoiceData.posting_date}`);
      const isPaid = Number(invoiceData.outstanding_amount ?? 0) === 0;
      lines.push(`Status: ${isPaid ? "Paid" : "Unpaid"}`);
      lines.push("");
    }
    const customerName = selectedCustomer?.name || selectedCustomer?.customerName;
    if (customerName) lines.push(`Customer: ${customerName}`);
    lines.push("");
    lines.push("Items:");
    for (const item of cartItems) {
      const rate = getEffectiveDisplayRate(item as any);
      const total = roundCurrency(rate * item.quantity);
      const name = item.item_name || item.name;
      lines.push(`  ${name}  ×${item.quantity}  @ ${formatCurrencyWithSymbol(rate, displayCurrencySymbol)}  =  ${formatCurrencyWithSymbol(total, displayCurrencySymbol)}`);
    }
    lines.push("");
    lines.push(`Grand Total: ${formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}`);
    return lines.join("\n");
  };

  const handleCopyOrder = () => {
    const text = buildOrderText();
    navigator.clipboard.writeText(text).then(() => {
      toast.success("Order copied to clipboard");
    }).catch(() => {
      toast.error("Failed to copy to clipboard");
    });
  };

  const getProcessedMessage = () => {
    const parameters: Record<string, string> = {
      customer_name: sharingData.name || "there",
      invoice_total: formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol),
      invoice_number: invoiceData?.name || "",
      company_name: "KLiK PoS",
      date: new Date().toLocaleDateString(),
    };
    return processTemplate(customMessage, parameters);
  };

  const getProcessedEmailMessage = () => {
    const parameters: Record<string, string | null> = {
      customer_name: sharingData.name || "Customer",
      customer: sharingData.name || "Customer",
      first_name: sharingData.name?.split(" ")[0] || "",
      last_name: sharingData.name?.split(" ").slice(1).join(" ") || "",
      address: typeof selectedCustomer?.address === "string" ? selectedCustomer.address : JSON.stringify(selectedCustomer?.address || {}),
      customer_address: typeof selectedCustomer?.address === "string" ? selectedCustomer.address : JSON.stringify(selectedCustomer?.address || {}),
      delivery_note: invoiceData?.name || "",
      grand_total: formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol),
      departure_time: new Date().toLocaleTimeString(),
      estimated_arrival: new Date(Date.now() + 30 * 60000).toLocaleTimeString(),
      driver_name: "Delivery Driver",
      cell_number: "+1234567890",
      vehicle: "Delivery Vehicle",
      invoice_total: formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol),
      invoice_number: invoiceData?.name || "",
      company_name: "KLiK PoS",
      date: new Date().toLocaleDateString(),
    };
    return processEmailTemplate(emailMessage, parameters);
  };

  const fetchCustomerDetails = async (customerId: string, existingEmail: string, existingPhone: string, existingName: string) => {
    try {
      const response = await fetch(`/api/method/klik_pos.api.customer.get_customer_info?customer_name=${customerId}`);
      const data = await response.json();
      if (data.message) {
        const customerData = data.message;
        setSharingData({
          email: existingEmail || customerData.email_id || "",
          phone: existingPhone || customerData.mobile_no || "",
          name: existingName || customerData.customer_name || customerData.name || "",
        });
      } else {
        setSharingData({ email: existingEmail, phone: existingPhone, name: existingName });
      }
    } catch (error) {
      console.error("Error fetching customer details:", error);
      setSharingData({ email: existingEmail, phone: existingPhone, name: existingName });
    }
  };

  useEffect(() => {
    if (isOpen && requiresSalespersonPin) {
      void ensureInitialized();
    }
  }, [isOpen, requiresSalespersonPin, ensureInitialized]);

  useEffect(() => {
    if (isOpen && !dueDate) {
      const today = new Date().toISOString().split("T")[0] || "";
      setDueDate(today);
    }
  }, [isOpen, dueDate]);

  // On a credit sale, the customer's payment terms (else the shortest) preselected; refetched
  // when the customer changes. A failed fetch or a site without templates keeps the date field.
  useEffect(() => {
    if (!isOpen || !isCreditSale) return;
    const customer = selectedCustomer?.id || undefined;
    let cancelled = false;
    // Submit waits for these: until they land, the due date shown is today, not the customer's.
    setCreditTermsLoading(true);
    getCreditTerms(customer)
      .then((terms) => {
        if (cancelled) return;
        setCreditTerms(terms);
        const handPicked = handPickedTerm.current;
        const kept = handPicked && handPicked.customer === customer ? handPicked.name : "";
        const picked = chooseTerm(terms, kept);
        setTermsTemplate(picked?.name ?? "");
        if (picked) setDueDate(picked.due_date);
      })
      .catch(() => {
        if (cancelled) return;
        setCreditTerms(null);
        toast.warning("Could not load the payment terms: check the due date before submitting", {
          toastId: "pos-credit-terms-failed",
        });
      })
      .finally(() => {
        if (!cancelled) setCreditTermsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, isCreditSale, selectedCustomer?.id]);

  const selectTerm = (name: string) => {
    const picked = chooseTerm(creditTerms, name);
    if (!picked) return;
    handPickedTerm.current = { customer: selectedCustomer?.id || undefined, name: picked.name };
    setTermsTemplate(picked.name);
    setDueDate(picked.due_date);
  };

  useEffect(() => {
    if (!isOpen) {
      initializedCreditDefaultRef.current = false;
      return;
    }

    if (initializedCreditDefaultRef.current) {
      return;
    }

    const shouldDefaultToCredit = allowCreditSales && defaultSalesType === "credit";
    setIsCreditSale(shouldDefaultToCredit);

    if (shouldDefaultToCredit) {
      setPaymentAmounts({});
      setLastModifiedMethodId(null);
    }

    initializedCreditDefaultRef.current = true;
  }, [isOpen, allowCreditSales, defaultSalesType]);

  useEffect(() => {
    // A template restored from a held order wins over the till default.
    if (isOpen && defaultTax && !selectedSalesTaxCharges && !checkoutExtras.salesTaxCharges) {
      setSelectedSalesTaxCharges(defaultTax);
    }
  }, [isOpen, defaultTax, selectedSalesTaxCharges, checkoutExtras.salesTaxCharges]);

  const setGrandTotalToDefaultMop = Boolean(Number(posDetails?.set_grand_total_to_default_mop || 0));

  useEffect(() => {
    if (isOpen && modes.length > 0 && !isCreditSale && Object.keys(paymentAmounts).length === 0) {
      const opening = openingPaymentAmounts(modes, checkoutPayableTotal, setGrandTotalToDefaultMop);
      const [method] = Object.keys(opening);
      if (method) {
        setLastModifiedMethodId(method);
        // Only if still empty: a resumed M-Pesa payment set in the same commit wins.
        setPaymentAmounts((prev) => (Object.keys(prev).length ? prev : opening));
      }
    }
  }, [isOpen, modes, checkoutPayableTotal, paymentAmounts, isCreditSale, setGrandTotalToDefaultMop]);

  useEffect(() => {
    if (!isOpen || invoiceSubmitted || isProcessingPayment || isCreditSale) {
      previousCheckoutGrandTotalRef.current = checkoutPayableTotal;
      return;
    }

    const previousTotal = previousCheckoutGrandTotalRef.current;
    if (Math.abs(previousTotal - checkoutPayableTotal) < 0.0001) {
      return;
    }

    // A push waiting on or paid by the customer fixes its method's amount; receipts likewise.
    const lockedMethod =
      mpesaFlow && (mpesaFlow.source === "c2b" || mpesaFlow.status === "in_progress" || mpesaFlow.status === "completed")
        ? mpesaFlow.modeOfPayment
        : null;
    setPaymentAmounts((prev) => followTotal(prev, previousTotal, checkoutPayableTotal, [CUSTOMER_CREDIT_METHOD, ...(lockedMethod ? [lockedMethod] : [])]));

    previousCheckoutGrandTotalRef.current = checkoutPayableTotal;
  }, [checkoutPayableTotal, isOpen, invoiceSubmitted, isProcessingPayment, isCreditSale, mpesaFlow]);

  useEffect(() => {
    if (invoiceSubmitted && invoiceData && print_receipt_on_order_complete) {
      setIsAutoPrinting(true);
      setTimeout(() => {
        handlePrintInvoice(invoiceData, { preventReprint: Boolean(posDetails?.custom_prevent_invoice_reprinting), posDetails });
        setIsAutoPrinting(false);
      }, 500);
    }
  }, [invoiceSubmitted, invoiceData, print_receipt_on_order_complete, posDetails?.custom_prevent_invoice_reprinting]);

  useEffect(() => {
    if (externalInvoiceData && sharingMode) {
      const email = externalInvoiceData.customer_address_doc?.email_id || externalInvoiceData.customer_email || externalInvoiceData.email_id || "";
      const phone = externalInvoiceData.mobile_no || externalInvoiceData.customer_address_doc?.mobile_no || externalInvoiceData.customer_address_doc?.phone || externalInvoiceData.customer_phone || "";
      const name = externalInvoiceData.customer_name || externalInvoiceData.customer || "";
      if ((!email || !phone) && externalInvoiceData.customer) {
        fetchCustomerDetails(externalInvoiceData.customer, email, phone, name);
      } else {
        setSharingData({ email, phone, name });
      }
    }
  }, [externalInvoiceData, sharingMode]);
  

  useEffect(() => {
    const loadWhatsAppTemplates = async () => {
      if (sharingMode === "whatsapp" && whatsappTemplates.length === 0) {
        setIsLoadingTemplates(true);
        try {
          const [templates, defaultTemplateName] = await Promise.all([fetchWhatsAppTemplates(), getDefaultWhatsAppTemplate()]);
          setWhatsappTemplates(templates);
          if (defaultTemplateName) {
            const defaultTemplate = templates.find((t) => t.name === defaultTemplateName);
            if (defaultTemplate) {
              setSelectedTemplate(defaultTemplate);
              setCustomMessage(defaultTemplate.template);
            }
          } else {
            setCustomMessage(getDefaultMessageTemplate());
          }
        } catch (error) {
          console.error("Error loading WhatsApp templates:", error);
          setCustomMessage(getDefaultMessageTemplate());
        } finally {
          setIsLoadingTemplates(false);
        }
      }
    };
    loadWhatsAppTemplates();
  }, [sharingMode, whatsappTemplates.length]);

  useEffect(() => {
    const loadEmailTemplates = async () => {
      if (sharingMode === "email" && emailTemplates.length === 0) {
        setIsLoadingEmailTemplates(true);
        try {
          const [templates, defaultTemplateName] = await Promise.all([fetchEmailTemplates(), getDefaultEmailTemplate()]);
          setEmailTemplates(templates);
          if (defaultTemplateName) {
            const defaultTemplate = templates.find((t) => t.name === defaultTemplateName);
            if (defaultTemplate) {
              setSelectedEmailTemplate(defaultTemplate);
              setEmailMessage(defaultTemplate.response_html || defaultTemplate.response);
            }
          } else {
            setEmailMessage(getDefaultEmailMessageTemplate());
          }
        } catch (error) {
          console.error("Error loading Email templates:", error);
          setEmailMessage(getDefaultEmailMessageTemplate());
        } finally {
          setIsLoadingEmailTemplates(false);
        }
      }
    };
    loadEmailTemplates();
  }, [sharingMode, emailTemplates.length]);

  const handleTemplateChange = (templateName: string) => {
    const template = whatsappTemplates.find((t) => t.name === templateName);
    if (template) {
      setSelectedTemplate(template);
      setCustomMessage(template.template);
    }
  };

  const handleEmailTemplateChange = (templateName: string) => {
    const template = emailTemplates.find((t) => t.name === templateName);
    if (template) {
      setSelectedEmailTemplate(template);
      setEmailMessage(template.response_html || template.response);
    }
  };

  const retryMpesaRequest = async () => {
    if (salespersonBlocksMpesa()) return;
    const action = stkRetryAction(getActiveMpesaPayment(), mpesaPhoneNumber, mpesaFlow?.phoneNumber);
    if (!action.send) {
      toast.error(action.reason);
      handleOpenMpesaOptions();
      return;
    }
    // Let go of the failed request first: while the flow still names it, the status poll
    // fetches it again and puts its failure back on screen.
    setMpesaFlow((prev) =>
      prev ? { ...prev, status: "idle", requestName: undefined, transactionId: undefined, message: undefined } : prev,
    );
    const sent = await initiateMpesaFlow(action.method, action.amount, action.phone);
    if (!sent) handleOpenMpesaOptions();
  };

  const renderLoyaltyRedemption = () => {
    const loyalty = selectedCustomer?.loyalty;
    if (!selectedCustomer || !loyalty?.enabled || !loyalty.loyalty_program) {
      return null;
    }

    const availablePoints = Number(loyalty.available_points ?? loyalty.loyalty_points ?? 0);
    const redeemableValue = Number(loyalty.redeemable_value || 0);
    const tier = loyalty.loyalty_program_tier || loyalty.customer_loyalty_program_tier;

    const locked = invoiceSubmitted || isProcessingPayment;

    return (
      <div className="min-w-[14rem] flex-[2]">
        <label
          className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300 mb-1"
          title={`${loyalty.loyalty_program_name || loyalty.loyalty_program}${tier ? ` · ${tier}` : ""}`}
        >
          <Award className="h-3.5 w-3.5" />
          Loyalty ({availablePoints.toLocaleString()} pts · {formatCurrencyWithSymbol(redeemableValue, displayCurrencySymbol)})
        </label>
        <div className="flex items-center gap-1.5">
          <StepperInput
            aria-label="Loyalty points"
            min="0"
            step="1"
            max={availablePoints}
            maxValue={availablePoints}
            wrapperClassName="min-w-0 flex-1"
            value={loyaltyPointsInput}
            {...selectAllOnFocus}
            onChange={(event) => handleLoyaltyPointsInputChange(event.target.value)}
            onStep={(next) => handleLoyaltyPointsInputChange(String(next))}
            disabled={locked || isApplyingLoyalty || availablePoints <= 0}
            placeholder="Points"
            className="w-full px-2 py-1.5 text-sm border border-amber-200 dark:border-amber-800 rounded-lg focus:ring-2 focus:ring-amber-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:cursor-not-allowed disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => void handleApplyLoyaltyRedemption()}
            disabled={locked || isApplyingLoyalty || availablePoints <= 0 || !appliedLoyalty}
            className="px-3 py-1.5 text-sm rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:text-gray-500 dark:disabled:text-gray-400 disabled:cursor-not-allowed font-medium"
          >
            {isApplyingLoyalty ? "Applying..." : "Apply"}
          </button>
          {appliedLoyalty && (
            <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 pl-2 pr-0.5 py-0.5 text-xs text-amber-800 dark:text-amber-200">
              {appliedLoyalty.loyalty_points.toLocaleString()} pts · -{formatCurrencyWithSymbol(appliedLoyalty.loyalty_amount, displayCurrencySymbol)}
              <button
                type="button"
                onClick={clearLoyaltyRedemption}
                disabled={locked}
                className="flex h-5 w-5 items-center justify-center rounded-full text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-50"
                title="Remove loyalty redemption"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
        </div>
      </div>
    );
  };

  const showLoyaltyRedemption = Boolean(
    selectedCustomer && selectedCustomer.loyalty?.enabled && selectedCustomer.loyalty?.loyalty_program,
  );

  const renderDeliveryChargeInput = (inline = false) => {
    const chargedByRule = Boolean(activeShippingRule);
    const locked = invoiceSubmitted || isProcessingPayment || chargedByRule;
    return (
      <div className={inline ? "flex items-center justify-between gap-3" : "min-w-[9rem] flex-1"}>
        <label
          className={inline ? "text-sm font-medium text-gray-600 dark:text-gray-400" : "block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1"}
        >
          Delivery charge
        </label>
        <StepperInput
          min="0"
          step="0.01"
          value={chargedByRule ? 0 : deliveryCharge}
          {...selectAllOnFocus}
          onChange={(e) => setDeliveryCharge(Math.max(0, Number(e.target.value || 0)))}
          onStep={(next) => setDeliveryCharge(next)}
          wrapperClassName={inline ? "w-32" : "w-full"}
          readOnly={chargedByRule}
          disabled={locked}
          title={
            chargedByRule
              ? "Charged by shipping rule"
              : deliveryChargeItemCode
                ? `Posted as service item: ${deliveryChargeItemCode}`
                : "Set Delivery Charge Item on POS Profile to post this amount as a service item."
          }
          aria-label="Delivery charge"
          className={`w-full ${inline ? "text-right" : ""} px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white ${locked ? "cursor-not-allowed opacity-50" : ""}`}
        />
      </div>
    );
  };

  const renderShippingRuleSelect = (extraClassName = "px-4 py-2") => {
    const locked = invoiceSubmitted || isProcessingPayment;
    // A recalled order may carry a rule that is no longer in the list; still show it.
    const options =
      activeShippingRule && !shippingRules.some((rule) => rule.name === activeShippingRule)
        ? [{ name: activeShippingRule, label: activeShippingRule }, ...shippingRules]
        : shippingRules;
    return (
      <select
        aria-label="Shipping rule"
        value={activeShippingRule || ""}
        onChange={(e) => {
          taxPreviewImmediateRef.current = true;
          setShippingRule(e.target.value || null);
        }}
        disabled={locked}
        className={`border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors focus:ring-2 focus:ring-beveren-500 ${activeShippingRule ? "" : "text-gray-500 dark:text-gray-400"} ${locked ? "cursor-not-allowed opacity-50" : "cursor-pointer"} ${extraClassName}`}
      >
        <option value="">Select shipping rule</option>
        {options.map((rule) => {
          const fixed = "calculate_based_on" in rule && rule.calculate_based_on === "Fixed";
          const amount = "shipping_amount" in rule ? Number(rule.shipping_amount || 0) : 0;
          return (
            <option key={rule.name} value={rule.name}>
              {rule.label || rule.name}
              {fixed && amount > 0 ? ` (${formatCurrencyWithSymbol(amount, displayCurrencySymbol)})` : ""}
            </option>
          );
        })}
      </select>
    );
  };

  // Applying puts the voucher's amount on the vouchers' total and takes the excess off the
  // other rows (a till's pre-filled cash, say) - never off a push in flight.
  const applyVoucher = (voucher: { note: string; original: string | null; available: number }) => {
    if (vouchersBlocked) {
      toast.error(`Vouchers unavailable: ${vouchersBlocked}.`);
      return;
    }
    if (appliedVouchers.some((applied) => applied.note === voucher.note)) {
      toast.info(`${voucher.note} is already applied.`);
      return;
    }
    const amount = voucherApplyAmount(voucher.available, checkoutPayableTotal, appliedTotal(appliedVouchers));
    if (amount <= 0) {
      toast.info("Nothing left to pay with a voucher.");
      return;
    }
    commitVouchers(
      addVoucher(appliedVouchers, { note: voucher.note, original: voucher.original, amount, available: voucher.available }),
    );
  };

  // The cashier spends part of an applied voucher; a larger amount trims the other rows.
  const resizeAppliedVoucher = (note: string, amount: number) => {
    commitVouchers(resizeVoucher(appliedVouchers, note, amount, checkoutPayableTotal));
  };

  const commitVouchers = (next: AppliedVoucher[]) => {
    setAppliedVouchers(next);
    setPaymentAmounts((prev) => {
      const withVouchers: PaymentAmount = { ...prev, [CUSTOMER_CREDIT_METHOD]: appliedTotal(next) };
      const preferred = Object.keys(withVouchers).filter(
        (methodId) => methodId !== CUSTOMER_CREDIT_METHOD && (withVouchers[methodId] || 0) > 0
      );
      return trimToPayable(withVouchers, checkoutPayableTotal, preferred, [
        CUSTOMER_CREDIT_METHOD,
        ...(stkLockedMethod ? [stkLockedMethod] : []),
      ]);
    });
  };

  const removeVoucher = (note: string) => {
    const next = appliedVouchers.filter((voucher) => voucher.note !== note);
    setAppliedVouchers(next);
    setPaymentAmounts((prev) => ({ ...prev, [CUSTOMER_CREDIT_METHOD]: appliedTotal(next) }));
  };

  // A Walk In sale paid with a named customer's voucher becomes that customer's sale -
  // Payment Reconciliation settles only a customer's own invoices.
  const switchSaleCustomer = async (customerName: string) => {
    const customer = await fetchCustomerRecord(customerName);
    if (!customer) {
      toast.error(`Could not load ${customerName}.`);
      return;
    }
    useProductStore.getState().setSelectedCustomer(customer as unknown as CartCustomer);
    toast.info(`Sale switched to ${customer.customerName || customerName}.`);
  };

  // Vouchers never outgrow the sale: a removed item, a discount or loyalty shrinks them.
  useEffect(() => {
    if (appliedTotal(appliedVouchers) <= roundCurrency(checkoutPayableTotal)) return;
    const capped = capVouchers(appliedVouchers, checkoutPayableTotal);
    setAppliedVouchers(capped);
    setPaymentAmounts((prev) => ({ ...prev, [CUSTOMER_CREDIT_METHOD]: appliedTotal(capped) }));
  }, [checkoutPayableTotal, appliedVouchers]);

  const renderVoucherButton = () => (
    <button
      type="button"
      onClick={() => setVoucherPanelOpen((open) => !open)}
      disabled={invoiceSubmitted || isProcessingPayment || Boolean(vouchersBlocked)}
      title={vouchersBlocked ? `Vouchers unavailable: ${vouchersBlocked}` : "Pay with a store-credit voucher"}
      className="px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      Voucher
      {appliedVouchers.length > 0
        ? ` · ${formatCurrencyWithSymbol(appliedTotal(appliedVouchers), displayCurrencySymbol)}`
        : customerCredit && customerCredit.total > 0
          ? ` · ${formatCurrencyWithSymbol(customerCredit.total, displayCurrencySymbol)} available`
          : ""}
    </button>
  );

  const renderVoucherPanel = () => (
    <VoucherPanel
      isOpen={voucherPanelOpen && !invoiceSubmitted}
      currencySymbol={displayCurrencySymbol}
      saleCustomer={{
        customer: String(selectedCustomer?.id || selectedCustomer?.name || ""),
        isWalkin: Boolean(selectedCustomer?.isWalkin),
      }}
      ownCredit={customerCredit}
      applied={appliedVouchers}
      disabled={isProcessingPayment || Boolean(vouchersBlocked)}
      onLookup={lookupCreditVoucher}
      onApply={applyVoucher}
      onRemove={removeVoucher}
      onResize={resizeAppliedVoucher}
      onSwitchCustomer={(customer) => void switchSaleCustomer(customer)}
      onClose={() => setVoucherPanelOpen(false)}
    />
  );

  // Leaving a sale whose push is paid. "Stay" is the focused default, so Enter (or a
  // scanner's trailing Enter) does not abandon it.
  const renderLeaveConfirm = () => (
    <ConfirmDialog
      isOpen={leaveConfirmOpen}
      onClose={() => setLeaveConfirmOpen(false)}
      onConfirm={() => {
        setLeaveConfirmOpen(false);
        onClose(false);
      }}
      title="The customer has already paid by M-Pesa"
      message="Leaving keeps this sale on Held with its payment - finish it from Held. Don't ring the same items up again, or the customer will pay twice."
      confirmText="Leave anyway"
      cancelText="Stay and finish"
    />
  );

  // One compact line in the Payment Methods header; the full detail is its tooltip.
  const renderMpesaStatusNotice = () => {
    if (!mpesaFlow) return null;

    let label: string;
    const detail: string[] = [];
    if (mpesaFlow.source === "c2b") {
      // Receipts pay in the order they were picked; what they hold beyond the M-Pesa
      // amount stays on them for a later sale.
      let left = paymentAmounts[mpesaFlow.modeOfPayment] || 0;
      let appliedTotal = 0;
      let staysTotal = 0;
      const receipts = mpesaFlow.c2bPayments ?? [];
      for (const payment of receipts) {
        const applied = roundCurrency(Math.min(payment.amount, Math.max(0, left)));
        left = roundCurrency(left - applied);
        const stays = roundCurrency(payment.amount - applied);
        appliedTotal = roundCurrency(appliedTotal + applied);
        staysTotal = roundCurrency(staysTotal + stays);
        detail.push(
          `${payment.transid || payment.name}: ${formatCurrencyWithSymbol(applied, displayCurrencySymbol)} applied` +
            (stays > 0 ? `, ${formatCurrencyWithSymbol(stays, displayCurrencySymbol)} stays on the receipt` : "")
        );
      }
      label =
        `Receipts: ${receipts.length} linked · ${formatCurrencyWithSymbol(appliedTotal, displayCurrencySymbol)} applied` +
        (staysTotal > 0 ? ` · ${formatCurrencyWithSymbol(staysTotal, displayCurrencySymbol)} stays` : "");
    } else {
      label =
        mpesaFlow.status === "completed"
          ? mpesaFlow.transactionId
            ? "STK: Paid"
            : receiptLookupEndedFor === mpesaFlow.requestName
              ? "STK: Paid - receipt needed"
              : RECEIPT_PENDING_MESSAGE
          : mpesaFlow.status === "failed"
            ? `STK failed${mpesaFlow.message ? ` - ${mpesaFlow.message}` : ""}`
            : "STK: Awaiting customer";
      detail.push(`Request: ${mpesaFlow.requestName}`);
      if (mpesaFlow.transactionId) detail.push(`Txn: ${mpesaFlow.transactionId}`);
    }
    if (mpesaFlow.message && mpesaFlow.status !== "failed") detail.push(mpesaFlow.message);

    const tone =
      mpesaFlow.status === "completed"
        ? "border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300"
        : mpesaFlow.status === "failed"
          ? "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300"
          : mpesaFlow.source === "c2b"
            ? "border-gray-300 bg-gray-50 text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            : "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300";

    return (
      <div className="flex items-center gap-1.5 min-w-0">
        <span
          title={detail.join("\n")}
          className={`inline-flex items-center min-w-0 rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}
        >
          <span className="truncate">{label}</span>
        </span>
        {mpesaFlow.source === "stk" && mpesaFlow.requestName && mpesaFlow.status !== "completed" && (
          <button
            type="button"
            title="Refresh status"
            aria-label="Refresh M-Pesa status"
            className="shrink-0 rounded-full border border-gray-300 dark:border-gray-600 p-1 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
            onClick={() => void refreshMpesaStatus()}
            disabled={isProcessingPayment}
          >
            <RefreshCw size={12} />
          </button>
        )}
        {mpesaFlow.source === "stk" &&
          mpesaFlow.status === "in_progress" &&
          mpesaFlow.requestName === checkOfferedFor && (
            <button
              type="button"
              className="shrink-0 rounded-full bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              onClick={() => {
                if (mpesaFlow.requestName) void checkWithMpesa(mpesaFlow.requestName);
              }}
              disabled={isCheckingMpesa || isProcessingPayment}
            >
              {isCheckingMpesa ? "Checking..." : "Check with M-Pesa"}
            </button>
          )}
        {mpesaFlow.source === "stk" && mpesaFlow.status === "failed" && (
          <button
            type="button"
            className="shrink-0 rounded-full bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            onClick={() => void retryMpesaRequest()}
            disabled={isProcessingPayment}
          >
            Send again
          </button>
        )}
      </div>
    );
  };

  if (!isOpen) return null;
  if (isLoading || posLoading) return <div className="p-6">Loading...</div>;
  if (error) return <div className="p-6 text-red-500">Error: {error}</div>;

  if (isMobile) {
    return (
      <div className={isFullPage ? "h-full bg-white dark:bg-gray-900 flex flex-col overflow-hidden" : "fixed inset-0 bg-white dark:bg-gray-900 z-50 flex flex-col overflow-hidden"}>
        {!isFullPage && (
          <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center justify-between z-10">
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
              {invoiceSubmitted ? (submissionQueued ? "Invoice Queued" : "Invoice Submitted") : isB2B ? "Submit Invoice" : "Payment"}
            </h1>
          </div>
        )}
        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
          <div className="p-4 space-y-4 [padding-bottom:calc(8rem+env(safe-area-inset-bottom))]">
            {invoiceSubmitted ? (
              <div className="space-y-4">
                <div className="flex items-center justify-center space-x-3 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                  <div className="text-green-600 dark:text-green-400 text-center">
                    <p className="font-semibold">
                      {submissionQueued ? "Invoice queued for background submission!" : "Invoice submitted successfully!"}
                    </p>
                    <p className="text-sm opacity-75">Total: {formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 justify-center">
                  {isAutoPrinting && (
                    <div className="flex items-center space-x-2 text-blue-600 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                      <Loader2 size={16} className="animate-spin" />
                      <span className="text-sm">Printing...</span>
                    </div>
                  )}
                  <button className="flex items-center space-x-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors" onClick={() => { handlePrintInvoice(invoiceData, { preventReprint: Boolean(posDetails?.custom_prevent_invoice_reprinting), posDetails }); void finalizeCompletedOrderState(); }}>
                    <Printer size={18} />
                    <span>Print</span>
                  </button>
                  {(posDetails?.custom_enable_qz_print === 1 || posDetails?.custom_enable_qz_print === '1' || posDetails?.custom_enable_qz_print === true) ? (
                    <button
                      className="flex items-center space-x-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                      onClick={() => {
                        const alreadyPrinted = Boolean(invoiceData?.custom_is_printed);
                        const preventReprint = Boolean(posDetails?.custom_prevent_invoice_reprinting);
                        if (alreadyPrinted && preventReprint) {
                          toast.error("Reprinting is not allowed for this invoice");
                          return;
                        }
                        void qzReprint(invoiceData?.name || invoiceData?.id || "");
                      }}
                    >
                      <QzPrintIcon size={18} />
                      <span>Reprint</span>
                    </button>
                  ) : ""}
                  <button className="flex items-center space-x-2 px-4 py-2 bg-blue-100 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/30 transition-colors" onClick={() => { void finalizeCompletedOrderState(() => { window.open(`mailto:${selectedCustomer?.email}?subject=Your%20Invoice&body=Dear%20${selectedCustomer?.name},%0A%0AHere%20is%20your%20invoice%20total:%20${formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}%0A%0AThank%20you.`); }); }}>
                    <MailPlus size={18} />
                    <span>Email</span>
                  </button>
                  <button className="flex items-center space-x-2 px-4 py-2 bg-green-100 dark:bg-green-900/20 text-beveren-600 dark:text-green-400 rounded-lg hover:bg-green-200 dark:hover:bg-green-900/30 transition-colors" onClick={() => { window.open(`https://wa.me/${selectedCustomer?.phone}?text=${encodeURIComponent(`Here is your invoice total: ${formatCurrencyWithSymbol(checkoutGrandTotal, displayCurrencySymbol)}`)}`, "_blank"); }}>
                    <MessageCirclePlus size={18} />
                    <span>WhatsApp</span>
                  </button>
                  <button className="flex items-center space-x-2 px-4 py-2 bg-purple-100 dark:bg-teal-900/20 text-teal-500 dark:text-teal-400 rounded-lg hover:bg-teal-200 dark:hover:bg-purple-900/30 transition-colors" onClick={() => window.open(`tel:${selectedCustomer?.phone}`)}>
                    <MessageSquarePlus size={18} />
                    <span>SMS</span>
                  </button>
                  <button className="flex items-center space-x-2 px-4 py-2 bg-purple-100 dark:bg-purple-900/20 text-p-600 dark:text-purple-400 rounded-lg hover:bg-purple-200 dark:hover:bg-purple-900/30 transition-colors" onClick={() => handleViewInvoice(invoiceData)}>
                    <Eye size={18} />
                    <span>View</span>
                  </button>
                </div>
                {invoiceData && (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 p-4">
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 text-center">Invoice Preview:</h4>
                    <div className="border border-gray-300 dark:border-gray-600 rounded p-3 bg-gray-50 dark:bg-gray-700 max-h-64 overflow-y-auto">
                      <DisplayPrintPreview invoice={invoiceData} />
                    </div>
                  </div>
                )}
                <div className="pt-4">
                  <button onClick={() => { void finalizeCompletedOrderState(() => onClose(true)); }} className="w-full py-3 bg-beveren-600 text-white rounded-lg font-medium hover:bg-beveren-700 transition-colors">
                    Start New Order
                  </button>
                </div>
              </div>
            ) : (
              <>
                <PaymentMethods
                  paymentMethods={paymentMethods}
                  invoiceSubmitted={invoiceSubmitted}
                  isProcessingPayment={isProcessingPayment}
                  onAmountChange={handleManualAmountChange}
                  onToggle={handleToggleMethod}
                  onReferenceChange={handleReferenceChange}
                  setActiveMethodId={setActiveMethodId}
                  references={paymentReferences}
                  lockedMethodIds={stkLockedMethod ? [stkLockedMethod] : []}
                  headerMiddle={showMpesaPanel ? null : renderMpesaStatusNotice()}
                  headerRight={
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                    {renderVoucherButton()}
                    {allowCreditSales ? (
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => toggleCreditSale()} disabled={invoiceSubmitted || isProcessingPayment} className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${isCreditSale ? "bg-teal-600 text-white dark:bg-teal-500" : "bg-teal-100 text-teal-800 hover:bg-teal-200 dark:bg-teal-950/40 dark:text-teal-200 dark:hover:bg-teal-950/60"} ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}>
                          {isCreditSale ? "Credit Sale Enabled" : "Is Credit Sale"}
                        </button>
                        {isCreditSale && usingTerms && (
                          <div className="flex items-center gap-1.5">
                            <label htmlFor="pos-credit-terms-mobile" className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
                              Terms:
                            </label>
                            <select
                              id="pos-credit-terms-mobile"
                              value={termsTemplate}
                              onChange={(e) => selectTerm(e.target.value)}
                              disabled={invoiceSubmitted || isProcessingPayment}
                              className={`max-w-[11rem] px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-xs ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}
                            >
                              {creditTerms?.templates.map((term) => (
                                <option key={term.name} value={term.name}>
                                  {termLabel(term)}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}
                        {isCreditSale && !usingTerms && (
                          <div className="flex items-center gap-1.5">
                            <label htmlFor="pos-credit-due-date-mobile" className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
                              Due:
                            </label>
                            <input
                              id="pos-credit-due-date-mobile"
                              type="date"
                              value={dueDate}
                              onChange={(e) => setDueDate(e.target.value)}
                              min={new Date().toISOString().split("T")[0]}
                              disabled={invoiceSubmitted || isProcessingPayment}
                              className={`px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-xs ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      // Rendered inert rather than hidden: a control that simply vanishes cannot
                      // tell anyone why. aria-disabled, NOT the disabled attribute — a disabled
                      // button emits no click, so the explanation would never fire.
                      <button
                        type="button"
                        aria-disabled="true"
                        onClick={() =>
                          toast.info(
                            posDetails?.name
                              ? `Credit sales are turned off for this POS Profile. Enable "Allow Credit Sales" on ${posDetails.name} to use them.`
                              : 'Credit sales are turned off for this POS Profile. Enable "Allow Credit Sales" to use them.',
                          )
                        }
                        className="px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap border border-dashed border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500 hover:text-gray-500 dark:hover:text-gray-400 transition-colors cursor-help"
                      >
                        Is Credit Sale
                      </button>
                    )}
                    </div>
                  }
                />
                {renderVoucherPanel()}
                {/* Remarks is on every till, so this row always shows. */}
                <div className="flex flex-wrap items-end gap-3">
                    {renderLoyaltyRedemption()}
                    {isDeliveryChargeEnabled && renderDeliveryChargeInput()}
                    {isShippingRuleEnabled && (
                      <div className="min-w-[12rem] flex-1">
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Shipping</label>
                        {renderShippingRuleSelect("w-full px-2 py-1.5 text-sm")}
                      </div>
                    )}
                    <TaxSection
                      invoiceSubmitted={invoiceSubmitted}
                      isProcessingPayment={isProcessingPayment}
                      allowDiscountChange={allowDiscountChange}
                      orderDiscountAmount={orderDiscountAmount}
                      orderDiscountPercentInput={orderDiscountPercentInput}
                      onOrderDiscountAmountChange={handleOrderDiscountAmountChange}
                      onOrderDiscountPercentChange={handleOrderDiscountPercentChange}
                    />
                    <RemarksInput value={remarks} onChange={setRemarks} disabled={invoiceSubmitted || isProcessingPayment} />
                </div>

                <TotalsSection
                  calculations={calculations}
                  displaySubtotal={displaySubtotal}
                  displayDiscount={displayDiscount}
                  displayTaxTotal={displayTaxTotal}
                  checkoutGrandTotal={checkoutGrandTotal}
                  loyaltyAmount={loyaltyAmount}
                  checkoutPayableTotal={checkoutPayableTotal}
                  totalPaidAmount={totalPaidAmount}
                  outstandingAmount={outstandingAmount}
                  displayCurrencySymbol={displayCurrencySymbol}
                  isB2B={isB2B}
                  backendTaxPreview={backendTaxPreview}
                  shippingAmount={shippingAmount}
                  netWeightLabel={netWeightLabel}
                />
                <div className="space-y-3 pt-6">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={enableBackgroundSubmission}
                        onChange={(e) => setEnableBackgroundSubmission(e.target.checked)}
                        disabled={invoiceSubmitted || isProcessingPayment}
                        className="w-5 h-5 rounded border-gray-300 text-beveren-600 focus:ring-beveren-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <div className="flex-1">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 block">
                          Submit Invoice in Background
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          Process invoice without waiting for response
                        </span>
                      </div>
                    </label>
                  </div>
                  {!reconciliation.ok && (
                    <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
                      <p className="font-semibold">This sale is on hold</p>
                      <p className="mt-1">{reconciliation.message}</p>
                    </div>
                  )}
                  <button id="pos-payment-submit-btn" onClick={handleCompletePayment} disabled={isActionButtonDisabled()} className={`w-full py-4 rounded-lg font-semibold disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center space-x-2 ${isB2B ? "bg-blue-600 hover:bg-blue-700 text-white" : "bg-green-600 hover:bg-green-700 text-white"}`}>
                    {isProcessingPayment ? (
                      <>
                        <Loader2 size={20} className="animate-spin" />
                        <span>{getActionButtonText()}</span>
                      </>
                    ) : (
                      <span>{getActionButtonText()}</span>
                    )}
                  </button>
                  {submitHint && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{submitHint}</p>}
                  {hasActiveMpesaPayment && (
                    <button
                      type="button"
                      onClick={() => void handleOpenMpesaOptions()}
                      disabled={isMpesaButtonDisabled()}
                      className="w-full py-4 rounded-lg font-semibold border border-emerald-600 text-emerald-700 disabled:border-gray-300 disabled:text-gray-400 disabled:cursor-not-allowed hover:bg-emerald-50 transition-colors"
                    >
                      {getMpesaButtonText()}
                    </button>
                  )}

                  <div className={`grid ${allow_holding_invoices ? "grid-cols-2" : "grid-cols-1"} gap-3`}>
                    <button
                      onClick={() => closeDialog(false)}
                      disabled={isProcessingPayment || isHoldingOrder}
                      className="py-3 px-4 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span>Cancel</span>
                    </button>
                    {allow_holding_invoices && (
                      <button onClick={handleHoldOrder} disabled={invoiceSubmitted || isProcessingPayment || isHoldingOrder} className={`py-3 px-4 border border-orange-500 text-orange-600 dark:text-orange-400 rounded-lg font-medium hover:bg-orange-50 dark:hover:bg-orange-900/20 transition-colors flex items-center justify-center space-x-2 ${invoiceSubmitted || isProcessingPayment || isHoldingOrder ? "cursor-not-allowed opacity-50" : ""}`}>
                        {isHoldingOrder ? (
                          <>
                            <Loader2 size={16} className="animate-spin" />
                            <span>Holding...</span>
                          </>
                        ) : (
                          <span>Hold</span>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
        <MpesaOptionsModal
          isOpen={showMpesaPanel}
          modeOfPayment={getActiveMpesaPayment()?.method || "M-Pesa"}
          amount={getActiveMpesaPayment()?.amount || 0}
          phoneNumber={mpesaPhoneNumber}
          currencySymbol={displayCurrencySymbol}
          searchTerm={mpesaSearchTerm}
          payments={mpesaPanelPayments}
          pendingCount={mpesaRegisterCount}
          selectedPaymentNames={selectedMpesaPayments.map((payment) => payment.name)}
          selectedTotal={selectedMpesaTotal}
          isLoadingPayments={isLoadingMpesaRegisterPayments}
          isProcessing={isProcessingPayment}
          onClose={() => setMpesaPanelDismissed(true)}
          onPhoneNumberChange={setMpesaPhoneNumber}
          onSearchChange={setMpesaSearchTerm}
          onTogglePayment={handleToggleMpesaPayment}
          onInitiateStk={() => void handleInitiateMpesaPayment()}
          stkPending={mpesaFlow?.source === "stk" && mpesaFlow.status === "in_progress"}
          stkPaid={mpesaFlow?.source === "stk" && mpesaFlow.status === "completed"}
          useReceipt={receiptPending}
          onAddPayments={() => void (receiptPending ? handleUsePushReceipt() : handleReconcileMpesaPayments())}
          status={renderMpesaStatusNotice()}
        />
        {renderLeaveConfirm()}
      </div>
    );
  }

  return (
    <div className="fixed inset-y-0 left-0 lg:left-20 right-0 z-[60] bg-white dark:bg-gray-900 flex flex-col overflow-hidden">
      {renderLeaveConfirm()}
        <PaymentHeader
          invoiceSubmitted={invoiceSubmitted}
          isAutoPrinting={isAutoPrinting}
          invoiceData={invoiceData}
          sharingMode={sharingMode}
          setSharingMode={setSharingMode}
          isProcessingPayment={isProcessingPayment}
          isHoldingOrder={isHoldingOrder}
          onClose={closeDialog}
          backLabel={backLabel}
          handleViewInvoice={handleViewInvoice}
          finalizeCompletedOrderState={(afterClear) => {
            void finalizeCompletedOrderState(afterClear);
          }}
          posDetails={posDetails}
          onCopyOrder={handleCopyOrder}
        />

        <div className="flex flex-1 min-h-0">
          <div className="flex-1 min-h-0 p-6 overflow-y-auto custom-scrollbar space-y-4">
            {invoiceSubmitted && sharingMode ? (
              <SharingInterface
                sharingMode={sharingMode}
                sharingData={sharingData}
                setSharingData={setSharingData}
                invoiceData={invoiceData}
                calculations={calculations}
                displayCurrencySymbol={displayCurrencySymbol}
                whatsappTemplates={whatsappTemplates}
                selectedTemplate={selectedTemplate}
                customMessage={customMessage}
                isLoadingTemplates={isLoadingTemplates}
                isEditingWhatsapp={isEditingWhatsapp}
                setIsEditingWhatsapp={setIsEditingWhatsapp}
                setSelectedTemplate={setSelectedTemplate}
                setCustomMessage={setCustomMessage}
                emailTemplates={emailTemplates}
                selectedEmailTemplate={selectedEmailTemplate}
                emailMessage={emailMessage}
                isLoadingEmailTemplates={isLoadingEmailTemplates}
                isEditingEmail={isEditingEmail}
                setIsEditingEmail={setIsEditingEmail}
                setSelectedEmailTemplate={setSelectedEmailTemplate}
                setEmailMessage={setEmailMessage}
                isSendingEmail={isSendingEmail}
                setIsSendingEmail={setIsSendingEmail}
                isSendingWhatsapp={isSendingWhatsapp}
                setIsSendingWhatsapp={setIsSendingWhatsapp}
                setSharingMode={setSharingMode}
                posDetails={posDetails}
                getProcessedMessage={getProcessedMessage}
                getProcessedEmailMessage={getProcessedEmailMessage}
                handleTemplateChange={handleTemplateChange}
                handleEmailTemplateChange={handleEmailTemplateChange}
              />
            ) : (
              <>
                <PaymentMethods
                  paymentMethods={paymentMethods}
                  invoiceSubmitted={invoiceSubmitted}
                  isProcessingPayment={isProcessingPayment}
                  onAmountChange={handleManualAmountChange}
                  onToggle={handleToggleMethod}
                  onReferenceChange={handleReferenceChange}
                  setActiveMethodId={setActiveMethodId}
                  references={paymentReferences}
                  lockedMethodIds={stkLockedMethod ? [stkLockedMethod] : []}
                  headerMiddle={showMpesaPanel ? null : renderMpesaStatusNotice()}
                  headerRight={
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                    {renderVoucherButton()}
                    {allowCreditSales ? (
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => toggleCreditSale()} disabled={invoiceSubmitted || isProcessingPayment} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isCreditSale ? "bg-teal-600 text-white dark:bg-teal-500" : "bg-teal-100 text-teal-800 hover:bg-teal-200 dark:bg-teal-950/40 dark:text-teal-200 dark:hover:bg-teal-950/60"} ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}>
                          {isCreditSale ? "Credit Sale Enabled" : "Is Credit Sale"}
                        </button>
                        {isCreditSale && usingTerms && (
                          <div className="flex items-center gap-2">
                            <label htmlFor="pos-credit-terms" className="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
                              Terms
                            </label>
                            <select
                              id="pos-credit-terms"
                              value={termsTemplate}
                              onChange={(e) => selectTerm(e.target.value)}
                              disabled={invoiceSubmitted || isProcessingPayment}
                              className={`max-w-[16rem] px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}
                            >
                              {creditTerms?.templates.map((term) => (
                                <option key={term.name} value={term.name}>
                                  {termLabel(term)}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}
                        {isCreditSale && !usingTerms && (
                          <div className="flex items-center gap-2">
                            <label htmlFor="pos-credit-due-date" className="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
                              Due Date
                            </label>
                            <input
                              id="pos-credit-due-date"
                              type="date"
                              value={dueDate}
                              onChange={(e) => setDueDate(e.target.value)}
                              min={new Date().toISOString().split("T")[0]}
                              disabled={invoiceSubmitted || isProcessingPayment}
                              className={`px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-beveren-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm ${invoiceSubmitted || isProcessingPayment ? "cursor-not-allowed opacity-50" : ""}`}
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      // Rendered inert rather than hidden: a control that simply vanishes cannot
                      // tell anyone why. aria-disabled, NOT the disabled attribute — a disabled
                      // button emits no click, so the explanation would never fire.
                      <button
                        type="button"
                        aria-disabled="true"
                        onClick={() =>
                          toast.info(
                            posDetails?.name
                              ? `Credit sales are turned off for this POS Profile. Enable "Allow Credit Sales" on ${posDetails.name} to use them.`
                              : 'Credit sales are turned off for this POS Profile. Enable "Allow Credit Sales" to use them.',
                          )
                        }
                        className="px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap border border-dashed border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500 hover:text-gray-500 dark:hover:text-gray-400 transition-colors cursor-help"
                      >
                        Is Credit Sale
                      </button>
                    )}
                    </div>
                  }
                />

                {renderVoucherPanel()}

                <div ref={mpesaOptionsPanelRef}>
                  <MpesaOptionsModal
                    isOpen={showMpesaPanel}
                    modeOfPayment={getActiveMpesaPayment()?.method || "M-Pesa"}
                    amount={getActiveMpesaPayment()?.amount || 0}
                    phoneNumber={mpesaPhoneNumber}
                    currencySymbol={displayCurrencySymbol}
                    searchTerm={mpesaSearchTerm}
                    payments={mpesaPanelPayments}
                    pendingCount={mpesaRegisterCount}
                    selectedPaymentNames={selectedMpesaPayments.map((payment) => payment.name)}
                    selectedTotal={selectedMpesaTotal}
                    isLoadingPayments={isLoadingMpesaRegisterPayments}
                    isProcessing={isProcessingPayment}
                    onClose={() => setMpesaPanelDismissed(true)}
                    onPhoneNumberChange={setMpesaPhoneNumber}
                    onSearchChange={setMpesaSearchTerm}
                    onTogglePayment={handleToggleMpesaPayment}
                    onInitiateStk={() => void handleInitiateMpesaPayment()}
          stkPending={mpesaFlow?.source === "stk" && mpesaFlow.status === "in_progress"}
          stkPaid={mpesaFlow?.source === "stk" && mpesaFlow.status === "completed"}
          useReceipt={receiptPending}
                    onAddPayments={() => void (receiptPending ? handleUsePushReceipt() : handleReconcileMpesaPayments())}
                    variant="panel"
                    status={renderMpesaStatusNotice()}
                  />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                  <OtherCharges>
                    {showLoyaltyRedemption && renderLoyaltyRedemption()}
                    {isDeliveryChargeEnabled && renderDeliveryChargeInput(true)}
                    {allowDiscountChange && (
                      <TaxSection
                        invoiceSubmitted={invoiceSubmitted}
                        isProcessingPayment={isProcessingPayment}
                        allowDiscountChange={allowDiscountChange}
                        orderDiscountAmount={orderDiscountAmount}
                        orderDiscountPercentInput={orderDiscountPercentInput}
                        onOrderDiscountAmountChange={handleOrderDiscountAmountChange}
                        onOrderDiscountPercentChange={handleOrderDiscountPercentChange}
                        inline
                      />
                    )}
                    <RemarksInput value={remarks} onChange={setRemarks} disabled={invoiceSubmitted || isProcessingPayment} inline />
                  </OtherCharges>

                  <div className="lg:col-start-2">
                    <TotalsSection
                      calculations={calculations}
                      displaySubtotal={displaySubtotal}
                      displayDiscount={displayDiscount}
                      displayTaxTotal={displayTaxTotal}
                      checkoutGrandTotal={checkoutGrandTotal}
                      loyaltyAmount={loyaltyAmount}
                      checkoutPayableTotal={checkoutPayableTotal}
                      totalPaidAmount={totalPaidAmount}
                      outstandingAmount={outstandingAmount}
                      displayCurrencySymbol={displayCurrencySymbol}
                      isB2B={isB2B}
                      backendTaxPreview={backendTaxPreview}
                      shippingAmount={shippingAmount}
                      netWeightLabel={netWeightLabel}
                      compact
                    />
                  </div>
                </div>

                <SalesPersonSection
                  requiresSalespersonPin={requiresSalespersonPin}
                  invoiceSubmitted={invoiceSubmitted}
                  currentSalesperson={currentSalesperson}
                  isLoading={isSalespersonRestoring || isVerifyingPin}
                  onOpenSalespersonModal={() => setShowSalespersonModal(true)}
                />

                <SalespersonAuthModal
                  isOpen={showSalespersonModal}
                  onClose={() => setShowSalespersonModal(false)}
                  title="Verify salesperson"
                  description="Switch or verify the salesperson assigned to this sale."
                />
              </>
            )}

          </div>

          <div className="w-[40%] min-w-[280px] xl:min-w-[320px] max-w-[520px] shrink-0 p-4 border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-y-auto custom-scrollbar">
            <InvoicePreview
              itemDiscounts={itemDiscounts}
              isTaxIncludedInBasicRate={isTaxIncludedInBasicRate}
              invoiceSubmitted={invoiceSubmitted}
              invoiceData={invoiceData}
              submittedInvoice={submittedInvoice}
              externalInvoiceData={externalInvoiceData}
              selectedCustomer={selectedCustomer}
              cartItems={cartItems}
              calculations={calculations}
              displaySubtotal={displaySubtotal}
              displayDiscount={displayDiscount}
              displayTaxTotal={displayTaxTotal}
              checkoutGrandTotal={checkoutGrandTotal}
              paymentAmounts={labelVoucherAmounts(paymentAmounts, CUSTOMER_CREDIT_METHOD)}
              displayCurrencySymbol={displayCurrencySymbol}
              isB2B={isB2B}
              isB2C={isB2C}
              currentDate={currentDate}
              extraCharges={reconciliation.extraCharges}
              taxBreakdown={backendTaxLines}
              shippingAmount={shippingAmount}
            />
          </div>
        </div>

        <div className="border-t border-gray-200 dark:border-gray-700 p-6 flex-shrink-0 bg-white dark:bg-gray-800">
          <div className="flex items-center justify-between gap-4">
            {(isDeliveryRequired || isShippingRuleEnabled) && (
              <div className="flex flex-1 flex-wrap items-center gap-3">
                {isDeliveryRequired && (
                  <DeliveryPersonnelCombobox
                    value={selectedDeliveryPersonnel}
                    onChange={setSelectedDeliveryPersonnel}
                    disabled={invoiceSubmitted || isProcessingPayment}
                    className="flex-1 min-w-[12rem] max-w-xs"
                  />
                )}
                {isShippingRuleEnabled && renderShippingRuleSelect("flex-1 min-w-[12rem] max-w-xs px-4 py-2")}
              </div>
            )}
            <div className={`flex items-center gap-4 ${isDeliveryRequired || isShippingRuleEnabled ? "" : "w-full justify-between"}`}>
              <label className="flex items-center gap-2 cursor-pointer group">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={enableBackgroundSubmission}
                    onChange={(e) => setEnableBackgroundSubmission(e.target.checked)}
                    disabled={invoiceSubmitted || isProcessingPayment}
                    className="w-4 h-4 rounded border-gray-300 text-beveren-600 focus:ring-beveren-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Submit Invoice in Background
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    Process invoice without waiting for response
                  </span>
                </div>
              </label>
              <div className="flex items-center gap-3">
               <ActionButtons
                  invoiceSubmitted={invoiceSubmitted}
                  isProcessingPayment={isProcessingPayment}
                  isHoldingOrder={isHoldingOrder}
                  isActionButtonDisabled={isActionButtonDisabled}
                  getActionButtonText={getActionButtonText}
                  onCompletePayment={handleCompletePayment}
                  onHoldOrder={handleHoldOrder}
                  onEditOrder={handleEditOrder}
                  onNewOrder={() => { void finalizeCompletedOrderState(() => onClose(true)); }}
                  isB2B={isB2B}
                  allow_holding_invoices={allow_holding_invoices}
                />
              </div>
            </div>
          </div>
          {submitHint && <p className="mt-2 text-right text-xs text-red-600 dark:text-red-400">{submitHint}</p>}
        </div>

    </div>
  );
}
