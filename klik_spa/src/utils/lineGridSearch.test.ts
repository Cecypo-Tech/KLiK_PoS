import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "react-toastify";
import { useCartStore } from "../stores/cartStore";
import { usePOSProfileStore } from "../stores/posProfileStore";
import { useProductStore } from "../stores/productStore";
import { latestOnly, scanAdd, searchGridItems, STALE } from "./lineGridSearch";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

const pen = { id: "PEN", item_code: "PEN", name: "Pen", price: 10, available: 10, is_stock_item: true, uom: "Nos" } as Record<string, unknown>;
const lines = () => useCartStore.getState().cartItems;
const profile = (extra: Record<string, unknown> = {}) =>
  usePOSProfileStore.setState({ posDetails: { custom_enable_loss_of_sale: 0, ...extra } as never });
const defer = <T,>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
    const sent = JSON.parse(new URL(url, "http://x").searchParams.get("cart_items") || "[]");
    return new Response(JSON.stringify({ message: { items: sent.map((s: { id: string; item_code: string }) => ({ id: s.id, item_code: s.item_code, price: 10 })) } }));
  }));
  profile();
  useCartStore.setState({ cartItems: [], quoteMode: false, selectedCustomer: null });
  useProductStore.setState({ fetchItemByIdentifier: (async (c: string) => (c === "PEN" ? pen : null)) as never });
  vi.mocked(toast.error).mockClear();
});

describe("latestOnly", () => {
  it("drops an earlier slower result", async () => {
    const wrap = latestOnly<string>();
    const a = defer<string>();
    const b = defer<string>();
    const r1 = wrap(a.promise);
    const r2 = wrap(b.promise);
    b.resolve("new");
    a.resolve("old");
    expect(await r1).toBe(STALE);
    expect(await r2).toBe("new");
  });
});

describe("scanAdd", () => {
  it("adds a matched code even when auto_add_item_to_cart is 0", async () => {
    profile({ auto_add_item_to_cart: 0 });
    const r = await scanAdd("PEN");
    expect(r).toEqual({ lineId: lines()[0]!.id });
    expect(lines()).toHaveLength(1);
  });

  it("two scans in flight both land in order", async () => {
    const first = defer<unknown>();
    useProductStore.setState({ fetchItemByIdentifier: (() => first.promise.then(() => pen)) as never });
    const p1 = scanAdd("PEN");
    useProductStore.setState({ fetchItemByIdentifier: (async () => pen) as never });
    const p2 = scanAdd("PEN");
    first.resolve(null);
    await Promise.all([p1, p2]);
    expect(lines()).toHaveLength(1);
    expect(lines()[0]!.quantity).toBe(2);
  });

  it("two scans make two lines when allow_multiple_items is 1", async () => {
    profile({ allow_multiple_items: 1 });
    await Promise.all([scanAdd("PEN"), scanAdd("PEN")]);
    expect(lines()).toHaveLength(2);
  });

  it("returns notFound and toasts for an unknown code", async () => {
    expect(await scanAdd("NOPE")).toEqual({ notFound: true });
    expect(toast.error).toHaveBeenCalledWith("No item found for NOPE");
    expect(lines()).toHaveLength(0);
  });

  it("returns refused when the cart refuses the add", async () => {
    useProductStore.setState({ fetchItemByIdentifier: (async () => ({ ...pen, available: 0 })) as never });
    expect(await scanAdd("PEN")).toEqual({ refused: true });
    expect(toast.error).not.toHaveBeenCalledWith("No item found for PEN");
  });
});

describe("searchGridItems", () => {
  it("passes customer and price list and leaves productStore.products untouched", async () => {
    const fetchProductsFromAPI = vi.fn().mockResolvedValue({ items: [pen] });
    const before = [{ id: "X" }] as never;
    useProductStore.setState({ fetchProductsFromAPI: fetchProductsFromAPI as never, products: before, searchQuery: "" });
    useCartStore.setState({ selectedCustomer: { id: "C1", sellingPriceList: "Retail" } as never });
    expect(await searchGridItems("pe")).toEqual([pen]);
    expect(fetchProductsFromAPI).toHaveBeenCalledWith(8, 0, "pe", "all", "C1", "Retail");
    expect(useProductStore.getState().products).toBe(before);
    expect(useProductStore.getState().searchQuery).toBe("");
  });
});
