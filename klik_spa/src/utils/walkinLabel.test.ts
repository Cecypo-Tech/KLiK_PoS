import { describe, expect, it } from "vitest";
import { walkinSubline } from "./walkinLabel";

describe("walkinSubline", () => {
  it("names the walk-in buyer under the customer", () => {
    expect(walkinSubline("Walk In", "Jane Wanjiku")).toBe("Jane Wanjiku");
  });
  it("is null when there is no name", () => {
    expect(walkinSubline("Walk In", "")).toBeNull();
    expect(walkinSubline("Walk In", "   ")).toBeNull();
    expect(walkinSubline("Walk In", undefined)).toBeNull();
  });
  it("is null when it would only repeat the customer", () => {
    expect(walkinSubline("Jane Wanjiku", " jane wanjiku ")).toBeNull();
  });
});
