import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const cart = {
  creditSale: true, quoteMode: false, selectedPriceList: null as string | null,
  selectedCustomer: { id: "C1", name: "FS Far", type: "company", sellingPriceList: "Wholesale" },
};
vi.mock("../../stores/cartStore", () => ({
  useCartStore: (sel: (s: typeof cart) => unknown) => sel(cart),
  saleTypeOf: (s: typeof cart) => (s.quoteMode ? "quote" : s.creditSale ? "credit" : "sale"),
}));
vi.mock("../../stores/posProfileStore", () => ({
  usePOSProfileStore: (sel: (s: unknown) => unknown) =>
    sel({ warehouse: null, posDetails: { warehouse: "Stores - DC", selling_price_list: "Retail" } }),
}));

import SaleContextStrip from "./SaleContextStrip";

describe("SaleContextStrip", () => {
  it("sale type, customer, warehouse, price list, in the top bar's order, nothing editable", () => {
    const html = renderToStaticMarkup(<SaleContextStrip />);
    const at = (t: string) => html.indexOf(t);
    expect(at("Credit Sale")).toBeGreaterThan(-1);
    expect(at("Credit Sale")).toBeLessThan(at("FS Far"));
    expect(at("FS Far")).toBeLessThan(at("Stores - DC"));
    expect(at("Stores - DC")).toBeLessThan(at("Wholesale")); // the customer's list when none is picked
    expect(html).toContain("bg-teal-600");
    expect(html).not.toMatch(/<(select|input|button)/);
  });
});
