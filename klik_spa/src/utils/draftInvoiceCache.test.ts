import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../stores/cartStore", () => ({ useCartStore: { setState: vi.fn() } }));

import { useCartStore } from "../stores/cartStore";
import { EMPTY_CHECKOUT_EXTRAS } from "./heldOrderPayload";

import {
  cacheDraftInvoiceItems,
  cacheHeldOrder,
  getOriginalHeldOrderMpesa,
  clearDraftInvoiceCache,
  forgetOriginalDraftInvoice,
  forgetOriginalHeldOrder,
  getOriginalDraftInvoiceId,
  getCachedDraftInvoiceItems,
  getOriginalHeldOrderId,
  hasCachedDraftInvoiceItems,
  loadCachedItemsToCart,
} from "./draftInvoiceCache";

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  (globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  };
});

/** Rewind the stored cache's timestamp, the way a long edit at the counter does. */
function ageCacheBy(minutes: number) {
  const raw = JSON.parse(store.get("draft-invoice-cache") as string);
  raw.timestamp -= minutes * 60 * 1000;
  store.set("draft-invoice-cache", JSON.stringify(raw));
}

describe("the link between the cart and the held order it came from", () => {
  it("survives an edit that runs longer than the cart cache", () => {
    // The bug: recall an order, serve somebody else, hold again twenty minutes later, and
    // no held_order_id was sent - so the server inserted a second Sales Order and left the
    // first one held. It only bit when the edit ran long, which is why it looked random.
    cacheHeldOrder("SAL-ORD-0001", [], null, 0);
    ageCacheBy(20);

    expect(getOriginalHeldOrderId()).toBe("SAL-ORD-0001");
  });

  it("is gone once the cart is cleared", () => {
    cacheHeldOrder("SAL-ORD-0001", [], null, 0);
    clearDraftInvoiceCache();

    expect(getOriginalHeldOrderId()).toBeNull();
  });

  it("is null when nothing was recalled", () => {
    expect(getOriginalHeldOrderId()).toBeNull();
  });
});

describe("the cart cache itself", () => {
  it("still expires, so an abandoned cart is not restored under a new sale", () => {
    cacheHeldOrder("SAL-ORD-0001", [], null, 0);
    ageCacheBy(20);

    expect(getCachedDraftInvoiceItems()).toBeNull();
    expect(hasCachedDraftInvoiceItems()).toBe(false);
  });

  it("is restorable while it is fresh", () => {
    cacheHeldOrder("SAL-ORD-0001", [], null, 0);

    expect(getCachedDraftInvoiceItems()?.originalHeldOrderId).toBe("SAL-ORD-0001");
    expect(hasCachedDraftInvoiceItems()).toBe(true);
  });
});

describe("forgetOriginalDraftInvoice", () => {
  it("drops the link to a draft that is no longer one, and keeps the cart", () => {
    cacheDraftInvoiceItems("POS-01190", [{ id: "A" } as never], null, 5);

    forgetOriginalDraftInvoice();

    expect(getOriginalDraftInvoiceId()).toBeNull();
    expect(getCachedDraftInvoiceItems()?.items).toHaveLength(1);
  });

  it("does nothing when there is no cache", () => {
    expect(() => forgetOriginalDraftInvoice()).not.toThrow();
    expect(getOriginalDraftInvoiceId()).toBeNull();
  });
});

describe("forgetOriginalHeldOrder", () => {
  it("drops the link to a held order that is gone, and keeps the cart", () => {
    cacheHeldOrder("SAL-ORD-0033", [{ id: "A" } as never], null, 0);

    forgetOriginalHeldOrder();

    expect(getOriginalHeldOrderId()).toBeNull();
    expect(getCachedDraftInvoiceItems()?.items).toHaveLength(1);
  });
});

describe("loadCachedItemsToCart and checkout's own state", () => {
  const item = { id: "A", item_code: "A", name: "A", quantity: 1, price: 10 } as never;
  const leftover = { deliveryCharge: 200, deliveryPersonnel: "DP-1", orderDiscountAmount: 50, salesTaxCharges: "VAT" };

  /** The state the loader would leave, starting from a cart that still holds `leftover`. */
  async function stateAfterLoad() {
    const setState = useCartStore.setState as unknown as ReturnType<typeof vi.fn>;
    setState.mockClear();
    await loadCachedItemsToCart();
    const updater = setState.mock.calls[0]![0] as (s: Record<string, unknown>) => Record<string, unknown>;
    return updater({ cartItems: [], checkoutExtras: leftover });
  }

  it("gives a recalled draft its own discount and none of the last sale's delivery or tax", async () => {
    cacheDraftInvoiceItems("ACC-SINV-1", [item], null, 10);

    expect((await stateAfterLoad()).checkoutExtras).toEqual({ ...EMPTY_CHECKOUT_EXTRAS, orderDiscountAmount: 10 });
  });

  it("brings a recalled draft's own remarks back, so submitting it does not clear them", async () => {
    cacheDraftInvoiceItems("ACC-SINV-1", [item], null, 0, "Paid by cheque 0012");

    expect((await stateAfterLoad()).checkoutExtras).toEqual({ ...EMPTY_CHECKOUT_EXTRAS, remarks: "Paid by cheque 0012" });
  });

  it("leaves a resumed held order's restored checkout state alone", async () => {
    cacheHeldOrder("SAL-ORD-1", [item], null, 10);

    expect((await stateAfterLoad()).checkoutExtras).toEqual(leftover);
  });
});

describe("a held order kept for its M-Pesa push", () => {
  it("remembers the push it was kept for, so checkout picks it up instead of charging again", () => {
    const request = { name: "MEXP-1", status: "Completed", amount: 4, phone_number: "254700000123", transaction_id: "UJ1" };
    cacheHeldOrder("SAL-ORD-9", [], null, 0, {}, { isMpesaOrder: true, request });

    expect(getOriginalHeldOrderMpesa()).toEqual({ isMpesaOrder: true, request });
  });

  it("is not an M-Pesa order unless the held order said so", () => {
    cacheHeldOrder("SAL-ORD-1", [], null, 0);

    expect(getOriginalHeldOrderMpesa()).toEqual({ isMpesaOrder: false, request: null });
  });
});
