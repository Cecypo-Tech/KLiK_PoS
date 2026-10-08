import { describe, expect, it } from "vitest";
import { transformCustomerInfo } from "./transformCustomerInfo";

describe("transformCustomerInfo", () => {
  it("carries the customer's delivery personnel", () => {
    expect(transformCustomerInfo({ name: "C-1", delivery_personnel: "DP-0001" }).deliveryPersonnel).toBe("DP-0001");
    expect(transformCustomerInfo({ name: "C-2" }).deliveryPersonnel).toBeNull();
  });
});
