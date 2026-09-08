import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../stores/cartStore", () => ({ useCartStore: { setState: vi.fn() } }));

import {
  cacheHeldOrder,
  clearDraftInvoiceCache,
  getCachedDraftInvoiceItems,
  getOriginalHeldOrderId,
  hasCachedDraftInvoiceItems,
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
