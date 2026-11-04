import { beforeEach, describe, expect, it, vi } from "vitest";

const toast = vi.hoisted(() => ({ warning: vi.fn(), info: vi.fn(), error: vi.fn(), success: vi.fn() }));
vi.mock("react-toastify", () => ({ toast }));

const getQuoteDetails = vi.hoisted(() => vi.fn());
vi.mock("../services/quotation", () => ({ getQuoteDetails }));
vi.mock("../services/salesOrder", () => ({ getHeldOrderDetails: vi.fn() }));

// A plain object standing in for the zustand cart store.
const cart = vi.hoisted(() => {
  const state: Record<string, unknown> = {};
  const reset = () => {
    for (const key of Object.keys(state)) delete state[key];
    Object.assign(state, {
      cartItems: [],
      quoteMode: true,
      selectedPriceList: "",
      exitQuoteMode: vi.fn(() => { state.quoteMode = false; }),
      refreshCartPricing: vi.fn(async () => {}),
      setWalkinDetails: vi.fn(),
      setExtraFields: vi.fn(),
      setShippingRule: vi.fn(),
      setCheckoutExtras: vi.fn(),
    });
  };
  reset();
  const setState = (patch: unknown) => {
    Object.assign(state, typeof patch === "function" ? (patch as (s: unknown) => object)(state) : patch);
  };
  return { state, reset, useCartStore: { getState: () => state, setState } };
});
vi.mock("../stores/cartStore", () => ({ useCartStore: cart.useCartStore }));
vi.mock("../stores/posProfileStore", () => ({ usePOSProfileStore: { getState: () => ({ posDetails: null }) } }));

import { addQuoteToCart } from "./quoteToCart";
import { clearDraftInvoiceCache, getOriginalHeldOrderId, getOriginalQuotationId } from "./draftInvoiceCache";

const store = new Map<string, string>();

const details = (overrides: Record<string, unknown> = {}) => ({
  success: true,
  name: "SAL-QTN-0001",
  customer: "CUST-1",
  customer_data: { id: "CUST-1", name: "Jane" },
  items: [{ item_code: "NAIL", item_name: "Nails", quantity: 3, los_qty: 0, price: 120, uom: "Kg" }],
  cart_meta: {},
  selling_price_list: "Standard Selling",
  grand_total: 360,
  currency: "KES",
  expired: false,
  ...overrides,
});

beforeEach(() => {
  store.clear();
  (globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  };
  cart.reset();
  vi.clearAllMocks();
});

describe("addQuoteToCart", () => {
  it("loads quoted price and records the quote id", async () => {
    getQuoteDetails.mockResolvedValue(details());

    expect(await addQuoteToCart("SAL-QTN-0001")).toBe(true);

    const items = cart.state.cartItems as Array<{ item_code: string; price: number; quantity: number }>;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ item_code: "NAIL", price: 120, quantity: 3 });
    expect(cart.state.selectedPriceList).toBe("Standard Selling");
    expect(getOriginalQuotationId()).toBe("SAL-QTN-0001");
    // A quote is not a held order: checkout must not try to convert a Sales Order.
    expect(getOriginalHeldOrderId()).toBeNull();
    expect(cart.state.refreshCartPricing).not.toHaveBeenCalled();
  });

  it("a line split against the till's stock warns of the Loss of Sale", async () => {
    getQuoteDetails.mockResolvedValue(details({
      items: [{ item_code: "NAIL", item_name: "Nails", quantity: 10, los_qty: 5, price: 120, uom: "Kg" }],
    }));

    await addQuoteToCart("SAL-QTN-0001");

    expect(toast.warning).toHaveBeenCalledWith("Only 10 Kg of Nails in stock: 5 recorded as Loss of Sale");
    expect(cart.state.cartItems).toEqual([expect.objectContaining({ quantity: 10, los_qty: 5 })]);
  });

  it("expired quote re-prices and toasts", async () => {
    getQuoteDetails.mockResolvedValue(details({ expired: true }));

    expect(await addQuoteToCart("SAL-QTN-0001")).toBe(true);

    expect(cart.state.refreshCartPricing).toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledWith("Quote expired - re-priced at today's prices");
  });

  it("loading leaves quote mode", async () => {
    getQuoteDetails.mockResolvedValue(details());

    await addQuoteToCart("SAL-QTN-0001");

    expect(cart.state.exitQuoteMode).toHaveBeenCalled();
    expect(cart.state.quoteMode).toBe(false);
  });

  it("a refused quote shows the server's reason and leaves the cart alone", async () => {
    getQuoteDetails.mockResolvedValue({ success: false, message: "Quote SAL-QTN-0001 has already been invoiced (SINV-1)." });

    expect(await addQuoteToCart("SAL-QTN-0001")).toBe(false);

    expect(toast.error).toHaveBeenCalledWith("Quote SAL-QTN-0001 has already been invoiced (SINV-1).");
    expect(cart.state.cartItems).toEqual([]);
    expect(cart.state.quoteMode).toBe(true);
    expect(getOriginalQuotationId()).toBeNull();
  });

  it("clearing the draft cache forgets the quote", async () => {
    getQuoteDetails.mockResolvedValue(details());
    await addQuoteToCart("SAL-QTN-0001");

    clearDraftInvoiceCache();

    expect(getOriginalQuotationId()).toBeNull();
  });
});
