import { describe, it, expect } from "vitest";
import { nextExpandedCartItemId } from "./toggleItemExpansion";

describe("nextExpandedCartItemId", () => {
  it("opens a line when nothing is open", () => {
    expect(nextExpandedCartItemId(null, "a")).toBe("a");
  });

  it("closes the currently open line when toggled again", () => {
    expect(nextExpandedCartItemId("a", "a")).toBeNull();
  });

  it("switches to a different line instead of allowing two open at once", () => {
    expect(nextExpandedCartItemId("a", "b")).toBe("b");
  });
});
