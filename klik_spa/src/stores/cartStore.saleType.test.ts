import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCartStore, saleTypeOf } from "./cartStore";
import { usePOSProfileStore } from "./posProfileStore";
import { persistedCartState } from "../utils/cartPersist";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

const s = () => useCartStore.getState();
const profile = (default_sales_type: string) =>
  usePOSProfileStore.setState({ posDetails: { custom_allow_credit_sales_as_pos: 1, default_sales_type } as never });

describe("sale type", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: { items: [] } }))));
    profile("Cash");
    useCartStore.setState({ cartItems: [], quoteMode: false, creditSale: false, selectedCustomer: { id: "C1", name: "C1" } as never });
  });

  it("setSaleType is exclusive", () => {
    s().setSaleType("credit");
    expect([s().creditSale, s().quoteMode, saleTypeOf(s())]).toEqual([true, false, "credit"]);
    s().setSaleType("quote");
    expect([s().creditSale, s().quoteMode, saleTypeOf(s())]).toEqual([false, true, "quote"]);
    s().setSaleType("sale");
    expect([s().creditSale, s().quoteMode, saleTypeOf(s())]).toEqual([false, false, "sale"]);
  });

  it("entering quote mode drops credit", () => {
    s().setSaleType("credit");
    s().enterQuoteMode();
    expect(s().creditSale).toBe(false);
  });

  it("a new customer resets credit to the profile default", async () => {
    s().setSaleType("credit");
    await s().setSelectedCustomer({ id: "C2", name: "C2" } as never);
    expect(s().creditSale).toBe(false);
  });

  it("re-selecting the same customer keeps the pick", async () => {
    s().setSaleType("credit");
    await s().setSelectedCustomer({ id: "C1", name: "C1" } as never);
    expect(s().creditSale).toBe(true);
  });

  it("profile default Credit starts a cleared cart on credit, never for walk-in", async () => {
    profile("Credit");
    s().clearCart();
    expect(s().creditSale).toBe(true);
    await s().setSelectedCustomer({ id: "WALK", name: "Walk-in", isWalkin: 1 } as never);
    expect(s().creditSale).toBe(false);
  });

  it("credit is never the default when the till disallows credit sales", () => {
    usePOSProfileStore.setState({ posDetails: { custom_allow_credit_sales_as_pos: 0, default_sales_type: "Credit" } as never });
    s().clearCart();
    expect(s().creditSale).toBe(false);
  });

  it("creditSale is dropped from storage once the sale completes", () => {
    expect(persistedCartState({ creditSale: true, saleCompleted: true } as never)).not.toHaveProperty("creditSale");
  });
});
