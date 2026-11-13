import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCartStore } from "./cartStore";
import { usePOSProfileStore } from "./posProfileStore";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

// 0.5 kg left on the shelf: the last of a weighed item.
const wire = (available = 0.5) => ({ id: "WIRE", item_code: "WIRE", name: "Wire", price: 10, available, is_stock_item: true, uom: "Kg" }) as never;
const lines = () => useCartStore.getState().cartItems;
const profile = (los: 0 | 1) => usePOSProfileStore.setState({ posDetails: { custom_enable_loss_of_sale: los } as never });

describe("the last part-unit of stock", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      const sent = JSON.parse(new URL(url, "http://x").searchParams.get("cart_items") || "[]");
      return new Response(JSON.stringify({ message: { items: sent.map((s: { id: string; item_code: string }) => ({ id: s.id, item_code: s.item_code, price: 10 })) } }));
    }));
    useCartStore.setState({ cartItems: [], quoteMode: false, selectedCustomer: null });
  });

  it("adds the 0.5 left when a click asks for 1", async () => {
    profile(0);
    await useCartStore.getState().addToCart(wire());
    expect(lines().map((l) => [l.quantity, l.los_qty ?? 0])).toEqual([[0.5, 0]]);
  });

  it("with Loss of Sale on, sells the 0.5 without recording a lost sale for the click", async () => {
    profile(1);
    await useCartStore.getState().addToCart(wire());
    expect(lines().map((l) => [l.quantity, l.los_qty ?? 0])).toEqual([[0.5, 0]]);
  });

  it("a typed 0.5 sells the last 0.5", async () => {
    profile(0);
    await useCartStore.getState().addToCartWithQuantity(wire(), 0.5);
    expect(lines().map((l) => l.quantity)).toEqual([0.5]);
  });

  it("a second click once the 0.5 is in the cart is still refused", async () => {
    profile(0);
    await useCartStore.getState().addToCart(wire());
    expect(await useCartStore.getState().addToCart(wire())).toBeNull();
    expect(lines().map((l) => l.quantity)).toEqual([0.5]);
  });

  it("+ on a line takes the last part-unit (1.5 in stock, line at 1 → 1.5)", async () => {
    profile(0);
    await useCartStore.getState().addToCart(wire(1.5));
    const id = lines()[0]!.id;
    await useCartStore.getState().adjustQuantity(id, 1);
    expect(lines().map((l) => [l.quantity, l.los_qty ?? 0])).toEqual([[1.5, 0]]);
  });

  it("+ with Loss of Sale on takes the last part-unit without booking LoS", async () => {
    profile(1);
    await useCartStore.getState().addToCart(wire(1.5));
    await useCartStore.getState().adjustQuantity(lines()[0]!.id, 1);
    expect(lines().map((l) => [l.quantity, l.los_qty ?? 0])).toEqual([[1.5, 0]]);
  });

  it("+ once the stock is all on the line is still refused (LoS off)", async () => {
    profile(0);
    await useCartStore.getState().addToCart(wire(1.5));
    const id = lines()[0]!.id;
    await useCartStore.getState().adjustQuantity(id, 1);
    await useCartStore.getState().adjustQuantity(id, 1);
    expect(lines().map((l) => l.quantity)).toEqual([1.5]);
  });

  it("- from a part-unit steps down by one as before", async () => {
    profile(0);
    await useCartStore.getState().addToCart(wire(1.5));
    const id = lines()[0]!.id;
    await useCartStore.getState().adjustQuantity(id, 1);
    await useCartStore.getState().adjustQuantity(id, -1);
    expect(lines().map((l) => l.quantity)).toEqual([0.5]);
  });
});
