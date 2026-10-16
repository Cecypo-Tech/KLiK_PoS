import { describe, expect, it } from "vitest";
import { warehouseAfterLoad } from "./pickedWarehouse";

const till = { name: "derick", warehouse: "Stores - DC", allow_warehouse_change: 1 };
const kept = { profile: "derick", user: "cashier@x", warehouse: "Warehouse - DC" };

describe("warehouseAfterLoad", () => {
  it("keeps the cashier's pick when the till reloads its details", () => {
    // A focus refresh or a page reload must not drop it: the cart was filled from it.
    expect(warehouseAfterLoad(till, "cashier@x", kept)).toBe("Warehouse - DC");
  });

  it("is the till's own warehouse when nothing was picked", () => {
    expect(warehouseAfterLoad(till, "cashier@x", null)).toBe("Stores - DC");
  });

  it("drops a pick made at another till or by another user", () => {
    expect(warehouseAfterLoad({ ...till, name: "other" }, "cashier@x", kept)).toBe("Stores - DC");
    expect(warehouseAfterLoad(till, "someone@x", kept)).toBe("Stores - DC");
  });

  it("drops the pick once the till no longer allows switching", () => {
    expect(warehouseAfterLoad({ ...till, allow_warehouse_change: 0 }, "cashier@x", kept)).toBe("Stores - DC");
  });
});
