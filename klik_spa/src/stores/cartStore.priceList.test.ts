import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCartStore } from "./cartStore";
import { usePOSProfileStore } from "./posProfileStore";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

describe("switching the price list", () => {
  beforeEach(() => {
    usePOSProfileStore.setState({ posDetails: { allow_price_list_switching: 1 } as never });
    useCartStore.setState({
      cartItems: [{ id: "PEN", item_code: "PEN", name: "Pen", quantity: 2, price: 10 } as never],
      selectedPriceList: null,
    });
  });

  it("re-prices the cart from the new list, once", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: { items: [{ id: "PEN", item_code: "PEN", price: 8 }] } })),
    );
    vi.stubGlobal("fetch", fetchMock);

    await useCartStore.getState().setSelectedPriceList("Wholesale");

    const pricing = fetchMock.mock.calls.filter(([url]) => String(url).includes("get_cart_pricing"));
    expect(pricing).toHaveLength(1);
    expect(String(pricing[0][0])).toContain("price_list=Wholesale");
    expect(useCartStore.getState().cartItems[0].price).toBe(8);
  });
});
