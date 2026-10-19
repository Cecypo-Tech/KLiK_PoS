import { describe, expect, it } from "vitest";
import { isReferenceMethod } from "./paymentIcons";

describe("isReferenceMethod", () => {
  it("asks for a reference on every type but Cash and Phone", () => {
    expect(isReferenceMethod("Bank")).toBe(true);
    expect(isReferenceMethod("General")).toBe(true);
    expect(isReferenceMethod("Default")).toBe(true);
    expect(isReferenceMethod("Cash")).toBe(false);
    expect(isReferenceMethod("Phone")).toBe(false);
  });
});
