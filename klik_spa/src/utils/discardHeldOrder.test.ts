import { describe, expect, it, vi } from "vitest";
import { discardHeldOrder } from "./discardHeldOrder";

class Gone extends Error {
  constructor() {
    super("gone");
    this.name = "HeldOrderGoneError";
  }
}

describe("discardHeldOrder", () => {
  it("does nothing for a cart that is not a held order", async () => {
    const del = vi.fn();
    expect(await discardHeldOrder(null, del)).toBeNull();
    expect(del).not.toHaveBeenCalled();
  });

  it("deletes the held order the cart was resumed from", async () => {
    const del = vi.fn().mockResolvedValue({ success: true });
    expect(await discardHeldOrder("SO-1", del)).toBeNull();
    expect(del).toHaveBeenCalledWith("SO-1");
  });

  it("lets the cart clear when the order is already gone", async () => {
    expect(await discardHeldOrder("SO-1", vi.fn().mockRejectedValue(new Gone()))).toBeNull();
  });

  it("keeps the cart and says why when the server refuses", async () => {
    const del = vi.fn().mockRejectedValue(new Error("M-Pesa request may still pay it"));
    expect(await discardHeldOrder("SO-1", del)).toBe("M-Pesa request may still pay it");
  });
});
