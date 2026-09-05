import { describe, it, expect } from "vitest";
import { appendDigit, deleteDigit, bufferToQuantity, MAX_QUANTITY_DIGITS } from "./quantityBuffer";

describe("appendDigit", () => {
  it("builds a quantity one digit at a time", () => {
    expect(appendDigit("", "3")).toBe("3");
    expect(appendDigit("3", "7")).toBe("37");
  });

  it("clears the buffer rather than truncating when the cap is exceeded", () => {
    // A wedge scanner types a long barcode. Truncating would leave "4901" and a
    // trailing Enter would add 4901 units; clearing makes it add 1 instead.
    expect(appendDigit("4901", "2")).toBe("");
  });

  it("accepts exactly the cap", () => {
    expect(appendDigit("490", "1")).toBe("4901");
    expect(MAX_QUANTITY_DIGITS).toBe(4);
  });

  it("ignores a leading zero so the buffer never starts at 0", () => {
    expect(appendDigit("", "0")).toBe("");
    expect(appendDigit("1", "0")).toBe("10");
  });

  it("ignores anything that is not a single digit", () => {
    expect(appendDigit("3", "a")).toBe("3");
    expect(appendDigit("3", "")).toBe("3");
    expect(appendDigit("3", "12")).toBe("3");
  });
});

describe("deleteDigit", () => {
  it("removes the last digit", () => {
    expect(deleteDigit("37")).toBe("3");
  });

  it("is a no-op on an empty buffer", () => {
    expect(deleteDigit("")).toBe("");
  });
});

describe("bufferToQuantity", () => {
  it("reads the buffer as a number", () => {
    expect(bufferToQuantity("37")).toBe(37);
  });

  it("treats an empty buffer as one, preserving today's behaviour", () => {
    expect(bufferToQuantity("")).toBe(1);
  });

  it("never returns less than one", () => {
    expect(bufferToQuantity("0")).toBe(1);
  });
});
