import { beforeEach, describe, expect, it, vi } from "vitest";
import { mergesSameItem, useCartStore } from "./cartStore";
import { usePOSProfileStore } from "./posProfileStore";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

const pen = (available = 10) => ({ id: "PEN", item_code: "PEN", name: "Pen", price: 10, available, is_stock_item: true, uom: "Nos" }) as never;
const lines = () => useCartStore.getState().cartItems;
const profile = (extra: Record<string, unknown> = {}) =>
  usePOSProfileStore.setState({ posDetails: { custom_enable_loss_of_sale: 0, ...extra } as never });

describe("same item: merge or new line", () => {
  beforeEach(() => {
    // Pricing echoes every requested line back at price 10.
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      const sent = JSON.parse(new URL(url, "http://x").searchParams.get("cart_items") || "[]");
      return new Response(JSON.stringify({ message: { items: sent.map((s: { id: string; item_code: string }) => ({ id: s.id, item_code: s.item_code, price: 10 })) } }));
    }));
    profile();
    useCartStore.setState({ cartItems: [], quoteMode: false, selectedCustomer: null });
  });

  it("merges into one line when allow_multiple_items is 0", async () => {
    await useCartStore.getState().addToCart(pen());
    await useCartStore.getState().addToCart(pen());
    expect(lines()).toHaveLength(1);
    expect(lines()[0]!.quantity).toBe(2);
  });

  it("merges by default even when allow_multiple_items is 1 (the setting is the grid's, passed explicitly)", async () => {
    profile({ allow_multiple_items: 1 });
    await useCartStore.getState().addToCart(pen());
    await useCartStore.getState().addToCart(pen());
    await useCartStore.getState().addToCartWithQuantity(pen(), 2);
    expect(lines()).toHaveLength(1);
    expect(lines()[0]!.quantity).toBe(4);
  });

  it("a typed grid pick (merge: mergesSameItem()) makes a second line when allow_multiple_items is 1", async () => {
    profile({ allow_multiple_items: 1 });
    await useCartStore.getState().addToCartQueued(pen(), { merge: mergesSameItem() });
    await useCartStore.getState().addToCartQueued(pen(), { merge: mergesSameItem() });
    expect(lines()).toHaveLength(2);
  });

  it("merge:false adds a second line", async () => {
    await useCartStore.getState().addToCart(pen(), { merge: false });
    await useCartStore.getState().addToCart(pen(), { merge: false });
    expect(lines()).toHaveLength(2);
    expect(lines().map((l) => l.item_code)).toEqual(["PEN", "PEN"]);
    expect(new Set(lines().map((l) => l.id)).size).toBe(2);
    expect(lines().map((l) => l.quantity)).toEqual([1, 1]);
  });

  it("explicit merge:false adds a line even when the setting is 0", async () => {
    await useCartStore.getState().addToCart(pen());
    await useCartStore.getState().addToCart(pen(), { merge: false });
    expect(lines()).toHaveLength(2);
  });

  it("addToCartWithQuantity honours merge:false", async () => {
    await useCartStore.getState().addToCartWithQuantity(pen(), 2);
    const id = await useCartStore.getState().addToCartWithQuantity(pen(), 3, { merge: false });
    expect(lines().map((l) => l.quantity)).toEqual([2, 3]);
    expect(id).toBe(lines()[1]!.id);
  });

  it("stock limit counts every line of the item", async () => {
    for (let i = 0; i < 3; i++) await useCartStore.getState().addToCart(pen(2), { merge: false });
    expect(lines()).toHaveLength(2);
  });

  it("returns the line id", async () => {
    const first = await useCartStore.getState().addToCart(pen());
    expect(first).toBe(lines()[0]!.id);
    expect(await useCartStore.getState().addToCart(pen())).toBe(first);
    expect(await useCartStore.getState().addToCartQueued(pen())).toBe(first);
  });

  it("returns null when refused", async () => {
    expect(await useCartStore.getState().addToCart(pen(0))).toBeNull();
  });

  it("two lines keep their own custom rate through refreshCartPricing", async () => {
    await useCartStore.getState().addToCart(pen(), { merge: false });
    await useCartStore.getState().addToCart(pen(), { merge: false });
    useCartStore.setState({ cartItems: lines().map((l, i) => ({ ...l, custom_rate: 5 + i }) as never) });
    await useCartStore.getState().refreshCartPricing();
    expect(lines().map((l) => (l as never as { custom_rate: number }).custom_rate)).toEqual([5, 6]);
  });

  it("each line keeps its own UOM price: rows match by position within the item code", async () => {
    await useCartStore.getState().addToCart(pen(), { merge: false });
    await useCartStore.getState().addToCart(pen(), { merge: false });
    useCartStore.setState({ cartItems: lines().map((l, i) => ({ ...l, uom: i ? "Box" : "Nos" })) });
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      const sent = JSON.parse(new URL(url, "http://x").searchParams.get("cart_items") || "[]");
      return new Response(JSON.stringify({ message: { items: sent.map((s: { id: string; item_code: string; uom: string }) => ({ id: s.id, item_code: s.item_code, price: s.uom === "Box" ? 120 : 10 })) } }));
    }));
    await useCartStore.getState().refreshCartPricing();
    expect(lines().map((l) => l.price)).toEqual([10, 120]);
  });

  it("pricing request sends the item code as id for every line", async () => {
    await useCartStore.getState().addToCart(pen(), { merge: false });
    await useCartStore.getState().addToCart(pen(), { merge: false });
    const url = (fetch as unknown as { mock: { calls: string[][] } }).mock.calls.at(-1)![0]!;
    const sent = JSON.parse(new URL(url, "http://x").searchParams.get("cart_items")!);
    expect(sent.map((s: { id: string }) => s.id)).toEqual(["PEN", "PEN"]);
  });

  it("insertion position Top puts the new line first", async () => {
    profile({ custom_cart_item_insertion_position: "Top" });
    await useCartStore.getState().addToCart(pen(), { merge: false });
    const second = await useCartStore.getState().addToCart(pen(), { merge: false });
    expect(lines()[0]!.id).toBe(second);
    expect(lines()).toHaveLength(2);
  });
});
