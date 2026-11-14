import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const profile = { posDetails: { custom_allow_to_create_and_edit_customers: 1, warehouse: "Stores - DC" } as Record<string, unknown>, warehouse: null, setWarehouse: () => {} };
const cart = { cartItems: [], selectedPriceList: null, setSelectedPriceList: () => {}, walkinDetails: {}, extraFields: {}, setAdditionalInfoOpen: () => {} };
vi.mock("react-dom", async (orig) => ({ ...(await orig<typeof import("react-dom")>()), createPortal: () => null }));
vi.mock("../../stores/posProfileStore", () => ({ usePOSProfileStore: () => profile }));
vi.mock("../../stores/cartStore", () => ({ useCartStore: (sel: (s: typeof cart) => unknown) => sel(cart) }));
vi.mock("../../stores/productStore", () => ({ useProductStore: (sel: (s: unknown) => unknown) => sel({ fetchProducts: () => {}, setSelectedCustomer: () => {} }) }));
vi.mock("../../hooks/useCustomers", () => ({ useCustomers: () => ({ customers: [], isLoading: false, refetch: () => {} }) }));
vi.mock("../../hooks/useCustomerPermission", () => ({ useCustomerPermission: () => ({ checkCustomerPermission: async () => true }) }));
vi.mock("../../hooks/useExtraFields", () => ({ useExtraFields: () => ({ fields: [] }) }));
vi.mock("react-phone-number-input", () => ({ parsePhoneNumber: () => undefined }));
vi.mock("react-select-country-list", () => ({ default: () => ({ getData: () => [] }) }));
vi.mock("../customer/AddCustomerModal", () => ({ default: () => null }));
vi.mock("../customer/OverdueWarningModal", () => ({ default: () => null }));
vi.mock("@/components/ui/alert-dialog", () => ({ AlertDialog: () => null, AlertDialogAction: () => null, AlertDialogContent: () => null, AlertDialogFooter: () => null, AlertDialogHeader: () => null, AlertDialogTitle: () => null, AlertDialogDescription: () => null }));

import { CustomerSearchSection } from "./CustomerSearchSection";
import type { Customer } from "../../types/customer";

const customer = { id: "C1", name: "FS Far", type: "company" } as unknown as Customer;
const render = (variant: "panel" | "bar", selected: Customer | null) =>
  renderToStaticMarkup(<CustomerSearchSection variant={variant} selectedCustomer={selected} onCustomerSelect={() => {}} onCustomerClear={() => {}} />);

describe("CustomerSearchSection side buttons", () => {
  it.each(["panel", "bar"] as const)("%s: Add New Customer and Additional Info sit beside the customer, without opening the dropdown", (variant) => {
    const html = render(variant, customer);
    expect(html).toContain('aria-label="Add New Customer"');
    expect(html).toContain('aria-label="Additional Info"');
    expect(html.indexOf("FS Far")).toBeLessThan(html.indexOf('aria-label="Add New Customer"'));
  });

  it("no customer picked: only Add New Customer; a till that may not create customers shows neither", () => {
    expect(render("bar", null)).toContain('aria-label="Add New Customer"');
    expect(render("bar", null)).not.toContain('aria-label="Additional Info"');
    profile.posDetails.custom_allow_to_create_and_edit_customers = 0;
    expect(render("panel", null)).not.toContain('aria-label="Add New Customer"');
  });
});
