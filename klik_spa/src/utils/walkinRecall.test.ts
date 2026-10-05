import { describe, expect, it } from "vitest";
import { recallablePhone, withRecalled } from "./walkinRecall";

describe("recallablePhone", () => {
  it("is a number with at least 9 digits, however typed", () => {
    expect(recallablePhone("0712 345 678")).toBe(true);
    expect(recallablePhone("+254712345678")).toBe(true);
    expect(recallablePhone("0712 34")).toBe(false);
    expect(recallablePhone("")).toBe(false);
  });
});

describe("withRecalled", () => {
  it("fills the name and PIN the cashier left blank", () => {
    expect(withRecalled({ name: "", taxId: " " }, { name: "Jane Wanjiku", tax_id: "A123456789Z" })).toEqual({
      name: "Jane Wanjiku",
      taxId: "A123456789Z",
    });
  });

  it("never overwrites what the cashier typed", () => {
    expect(withRecalled({ name: "John", taxId: "" }, { name: "Jane Wanjiku", tax_id: "A123456789Z" })).toEqual({
      name: "John",
      taxId: "A123456789Z",
    });
  });

  it("leaves blanks blank when the last sale had nothing", () => {
    expect(withRecalled({ name: "", taxId: "" }, {})).toEqual({ name: "", taxId: "" });
  });
});
