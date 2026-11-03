import { describe, expect, it } from "vitest";
import { pinToLookUp } from "./taxPin";

describe("pinToLookUp", () => {
  it("waits until the whole KRA PIN is typed", () => {
    expect(pinToLookUp("A12345678", "")).toBeNull();
    expect(pinToLookUp("A123456789", "")).toBeNull();
  });
  it("looks up a complete PIN, in any case", () => {
    expect(pinToLookUp(" a123456789p ", "")).toBe("A123456789P");
  });
  it("does not look the same PIN up twice", () => {
    expect(pinToLookUp("A123456789P", "A123456789P")).toBeNull();
  });
});
