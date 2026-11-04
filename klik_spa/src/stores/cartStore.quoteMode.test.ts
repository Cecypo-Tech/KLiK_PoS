import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCartStore } from "./cartStore";
import { usePOSProfileStore } from "./posProfileStore";
import { persistedCartState } from "../utils/cartPersist";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

const item = { id: "PEN", item_code: "PEN", name: "Pen", price: 10, available: 10, is_stock_item: true, uom: "Nos" } as never as Record<string, unknown>;
const line = () => useCartStore.getState().cartItems[0]!;

describe("quote mode lifts the stock limit", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: { items: [] } }))));
    usePOSProfileStore.setState({ posDetails: { custom_enable_loss_of_sale: 0 } as never });
    useCartStore.setState({ cartItems: [], quoteMode: false, selectedCustomer: null });
  });

  it("adds 15 of a 10-in-stock item", async () => {
    useCartStore.getState().enterQuoteMode();
    await useCartStore.getState().addToCartWithQuantity(item as never, 15);
    expect(line().quantity).toBe(15);
    expect(line().los_qty ?? 0).toBe(0);
  });

  it("does not split into loss of sale when LoS is on", async () => {
    usePOSProfileStore.setState({ posDetails: { custom_enable_loss_of_sale: 1 } as never });
    useCartStore.getState().enterQuoteMode();
    await useCartStore.getState().addToCartWithQuantity(item as never, 15);
    expect(line().quantity).toBe(15);
    expect(line().los_qty ?? 0).toBe(0);
  });

  it("sale mode still clamps", async () => {
    // Sale mode refuses an over-stock add outright (cart stays empty).
    expect(await useCartStore.getState().addToCartWithQuantity(item as never, 15)).toBeNull();
    expect(useCartStore.getState().cartItems).toHaveLength(0);
  });

  it("after exitQuoteMode the line follows normal stock rules again", async () => {
    useCartStore.getState().enterQuoteMode();
    await useCartStore.getState().addToCartWithQuantity(item as never, 15);
    useCartStore.getState().exitQuoteMode();
    await useCartStore.getState().adjustQuantity("PEN", 1);
    const afterExit = { q: line()?.quantity, los: line()?.los_qty ?? 0 };

    // The same over-stock line, never in quote mode.
    useCartStore.setState({ cartItems: [{ ...item, quantity: 15 } as never], quoteMode: false });
    await useCartStore.getState().adjustQuantity("PEN", 1);
    expect({ q: line()?.quantity, los: line()?.los_qty ?? 0 }).toEqual(afterExit);
  });

  it("survives persistence", () => {
    expect(persistedCartState({ ...useCartStore.getState(), quoteMode: true }).quoteMode).toBe(true);
  });
});
