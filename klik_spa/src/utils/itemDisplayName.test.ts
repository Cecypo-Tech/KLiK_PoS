import { describe, it, expect } from "vitest";
import { getItemDisplayName } from "./itemDisplayName";

describe("getItemDisplayName", () => {
  it("returns the item name when the toggle is off", () => {
    expect(getItemDisplayName({ name: "Widget", item_code: "WID-1" }, false)).toBe("Widget");
  });

  it("returns the item name when the toggle is omitted", () => {
    expect(getItemDisplayName({ name: "Widget", item_code: "WID-1" })).toBe("Widget");
  });

  it("returns the item code when the toggle is on", () => {
    expect(getItemDisplayName({ name: "Widget", item_code: "WID-1" }, true)).toBe("WID-1");
  });

  it("falls back to id when item_code is missing and the toggle is on", () => {
    expect(getItemDisplayName({ name: "Widget", id: "abc123" }, true)).toBe("abc123");
  });

  it("falls back to name when neither item_code nor id exist, even with the toggle on", () => {
    expect(getItemDisplayName({ name: "Widget" }, true)).toBe("Widget");
  });

  it("reads item_name when name is absent", () => {
    expect(getItemDisplayName({ item_name: "Widget" })).toBe("Widget");
  });
});
