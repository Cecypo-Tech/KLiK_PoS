import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { CartItem } from "../../../types";
import type { POSDetails } from "../../stores/posProfileStore";
import LineGrid from "./LineGrid";

vi.mock("react-toastify", () => ({ toast: { error: vi.fn(), warning: vi.fn() } }));
vi.mock("../../utils/lineGridSearch", () => ({
  latestOnly: () => (p: Promise<unknown>) => p,
  STALE: Symbol("stale"),
  searchGridItems: vi.fn(async () => []),
  scanAdd: vi.fn(),
}));

const line = (id: string, name: string, description?: string) =>
  ({ id, item_code: id, name, category: "", price: 100, image: "", quantity: 1, description }) as CartItem;

const render = (items: CartItem[], pos: Partial<POSDetails> = {}, itemDiscounts = {}) =>
  renderToStaticMarkup(
    <LineGrid
      items={items}
      itemDiscounts={itemDiscounts}
      selectedId={null}
      onSelect={() => {}}
      onUpdateQuantity={() => {}}
      onCustomRateChange={() => {}}
      onDiscountChange={() => {}}
      onRemoveItem={() => {}}
      onUOMChange={() => {}}
      onOpenDescription={() => {}}
      onPickItem={async () => null}
      currencySymbol="KES"
      posDetails={{ name: "P", allow_rate_change: 1, allow_discount_change: 1, ...pos } as POSDetails}
    />,
  );

describe("LineGrid", () => {
  it("renders Item, Qty, UOM, Rate, Disc %, Total headers", () => {
    const html = render([line("A", "Apple")]);
    for (const h of ["Item", "Qty", "UOM", "Rate", "Disc %", "Total"]) expect(html).toContain(`>${h}</th>`);
  });

  it("shows the line's unit in the UOM column (a picker appears once the item has more than one)", () => {
    const html = render([{ ...line("A", "Apple"), uom: "Box" }]);
    expect(html).toMatch(/data-uom-cell="A"[^>]*>[^<]*<span[^>]*>Box<\/span>/);
  });

  it("chips a line's Loss of Sale left of its qty, when the till records LoS", () => {
    const los = { ...line("A", "Apple"), quantity: 4, los_qty: 6 } as CartItem;
    expect(render([los], { custom_enable_loss_of_sale: 1 })).toMatch(/data-los-chip="A"[^>]*>LoS 6<\/span>.*data-col="qty"/);
    expect(render([los])).not.toContain("data-los-chip");
    expect(render([line("A", "Apple")], { custom_enable_loss_of_sale: 1 })).not.toContain("data-los-chip");
  });

  it("shows a description as an italic second line, and nothing when there is none", () => {
    expect(render([line("A", "Apple", "Green ones")])).toMatch(/<[^>]*class="[^"]*italic[^"]*"[^>]*>Green ones</);
    expect(render([line("A", "Apple")])).not.toContain("italic");
  });

  it("puts the entry row first for Top and last for Bottom", () => {
    const items = [line("A", "Apple"), line("B", "Banana")];
    const top = render(items, { custom_cart_item_insertion_position: "Top" });
    expect(top.indexOf("data-entry-row")).toBeLessThan(top.indexOf("Apple"));
    const bottom = render(items, { custom_cart_item_insertion_position: "Bottom" });
    expect(bottom.indexOf("data-entry-row")).toBeGreaterThan(bottom.indexOf("Banana"));
  });

  it("makes Rate and Disc readOnly when the till forbids changing them", () => {
    const cell = (html: string, col: string) => html.match(new RegExp(`<input[^>]*data-col="${col}"[^>]*>`))![0];
    const locked = render([line("A", "Apple")], { allow_rate_change: 0, allow_discount_change: 0 });
    expect(cell(locked, "rate")).toContain("readOnly");
    expect(cell(locked, "disc")).toContain("readOnly");
    const open = render([line("A", "Apple")]);
    expect(cell(open, "rate")).not.toContain("readOnly");
    expect(cell(open, "disc")).not.toContain("readOnly");
  });

  it("a custom-rate line shows the pre-discount rate, the % of it, and the discounted total", () => {
    const html = render([line("A", "Apple")], {}, { A: { customRate: 80, discountAmount: 4 } });
    const val = (col: string) => html.match(new RegExp(`<input[^>]*data-col="${col}"[^>]*value="([^"]*)"`))?.[1]
      ?? html.match(new RegExp(`<input[^>]*value="([^"]*)"[^>]*data-col="${col}"`))![1];
    expect(val("rate")).toBe("80.00");
    expect(val("disc")).toBe("5.00");
    expect(html).toContain("76.00");
  });
});
