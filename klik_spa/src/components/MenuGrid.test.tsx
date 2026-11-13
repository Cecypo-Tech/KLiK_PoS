import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import MenuGrid from "./MenuGrid";

vi.mock("react-toastify", () => ({ toast: { info: vi.fn() } }));
vi.mock("../hooks/useAuth", () => ({ useAuth: () => ({ user: { name: "u@x", full_name: "U X" }, logout: vi.fn() }) }));
vi.mock("../hooks/useTheme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
vi.mock("../providers/ProductProvider", () => ({
  useProduct: () => ({ searchQuery: "", filteredItems: [], defaultView: "grid", useScannerOnly: false, stockUnavailable: {}, lossOfSaleEnabled: false }),
}));
vi.mock("../stores/posProfileStore", () => ({ usePOSProfileStore: () => ({ posDetails: { name: "Till 1", warehouse: "Stores" } }) }));
vi.mock("../stores/salespersonStore", () => ({ useSalespersonStore: () => ({ ensureInitialized: vi.fn() }) }));
vi.mock("./CategoryTabs", () => ({ default: () => <div data-stub="category-tabs" /> }));
vi.mock("./ProductGrid", () => ({ default: () => <div data-stub="product-grid" /> }));
vi.mock("./SearchBar", () => ({ default: () => <input id="pos-search-input" /> }));
vi.mock("./SwitchProfileItem", () => ({ default: () => null }));
vi.mock("./dialog/SalespersonAuthModal", () => ({ default: () => null }));
vi.mock("./QuickEntryDialog", () => ({ default: () => null }));
vi.mock("./order/CustomerSearchSection", () => ({ CustomerSearchSection: ({ variant }: { variant?: string }) => <div data-stub="customer" data-variant={variant} /> }));
vi.mock("./KeyboardShortcutsPanel", () => ({ default: ({ mode }: { mode?: string }) => <div data-stub="shortcuts" data-mode={mode ?? "cart"} /> }));

const render = (headerOnly?: boolean) =>
  renderToStaticMarkup(<MemoryRouter><MenuGrid headerOnly={headerOnly} onScanBarcode={() => {}} /></MemoryRouter>);

describe("MenuGrid", () => {
  it("classic: search box, category tabs, product list, cart help", () => {
    const html = render();
    for (const s of ['id="pos-search-input"', 'data-stub="category-tabs"', 'data-stub="product-grid"', 'data-mode="cart"', 'title="Grid View"']) {
      expect(html).toContain(s);
    }
    expect(html).not.toContain('data-stub="customer"'); // the cart panel carries it on this layout
  });

  it("headerOnly: the customer strip leads the bar; no search, tabs, product list or view toggle; grid help; a scan button", () => {
    const html = render(true);
    expect(html.indexOf('data-variant="bar"')).toBeGreaterThan(-1);
    expect(html.indexOf('data-variant="bar"')).toBeLessThan(html.indexOf('title="Scan Barcode"'));
    for (const s of ['id="pos-search-input"', 'data-stub="category-tabs"', 'data-stub="product-grid"', 'title="Grid View"']) {
      expect(html).not.toContain(s);
    }
    for (const s of ['id="pos-shortcuts-btn"', 'data-mode="grid"', 'title="Scan Barcode"', 'title="Keyboard shortcuts (?)"', 'aria-label="Quick entry"', "Till 1", 'aria-label="User menu"']) {
      expect(html).toContain(s);
    }
  });
});
