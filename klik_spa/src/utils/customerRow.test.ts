import { describe, expect, it } from "vitest";
import { customerRowDetails } from "./customerRow";

describe("customerRowDetails", () => {
  it("is phone | email | town, skipping blanks", () => {
    expect(customerRowDetails({ phone: "+254752666333", email: "mike@jones.com", address: { city: "Nairobi" } })).toBe(
      "+254752666333 | mike@jones.com | Nairobi",
    );
    expect(customerRowDetails({ phone: "N/A", email: "", address: { city: "Kerugoya" } })).toBe("Kerugoya");
    expect(customerRowDetails({ phone: "", email: "" })).toBe("");
  });
});
