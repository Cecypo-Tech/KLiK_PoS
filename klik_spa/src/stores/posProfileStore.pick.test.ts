import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePOSProfileStore } from "./posProfileStore";

const details = { name: "derick", warehouse: "Stores - DC", allow_warehouse_change: 1 };

describe("the picked warehouse", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    });
    vi.stubGlobal("window", { klik_user: "cashier@x" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: details }))));
    usePOSProfileStore.setState({ posDetails: details as never, warehouse: null, isAuthenticated: true, isLoading: false });
  });

  it("survives the till refetching its details, as on every window focus", async () => {
    usePOSProfileStore.getState().setWarehouse("Warehouse - DC");
    await usePOSProfileStore.getState().fetchPOSDetails(true);
    expect(usePOSProfileStore.getState().warehouse).toBe("Warehouse - DC");
  });

  it("survives the cache being cleared on unload and the details loading again", async () => {
    usePOSProfileStore.getState().setWarehouse("Warehouse - DC");
    usePOSProfileStore.getState().clearCache();
    usePOSProfileStore.setState({ isAuthenticated: true });
    await usePOSProfileStore.getState().fetchPOSDetails(true);
    expect(usePOSProfileStore.getState().warehouse).toBe("Warehouse - DC");
  });
});
