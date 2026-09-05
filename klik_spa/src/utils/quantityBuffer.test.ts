import { describe, it, expect } from "vitest";
import { appendDigit, deleteDigit, bufferToQuantity, MAX_QUANTITY_DIGITS, OVERFLOW } from "./quantityBuffer";

describe("appendDigit", () => {
  it("builds a quantity one digit at a time", () => {
    expect(appendDigit("", "3")).toBe("3");
    expect(appendDigit("3", "7")).toBe("37");
  });

  it("goes sticky-overflow rather than truncating when the cap is exceeded", () => {
    // A wedge scanner types a long barcode. Truncating would leave "4901" and a
    // trailing Enter would add 4901 units; overflowing sticks so Enter adds 1
    // instead, no matter how many more digits the scanner still has to type.
    expect(appendDigit("4901", "2")).toBe(OVERFLOW);
  });

  it("stays overflowed for every digit after the cap, instead of cycling", () => {
    // This is the bug: a naive "reset to empty on overflow" cycles with a period
    // of MAX_QUANTITY_DIGITS + 1, so a barcode longer than that leaves a plausible
    // -looking tail in the buffer instead of failing safe.
    const ean13 = "4901234567894";
    const result = [...ean13].reduce(appendDigit, "");
    expect(bufferToQuantity(result)).toBe(1);
  });

  it("stays overflowed for a 14-digit code (length ≡ 4 mod 5, the worst case for cycling)", () => {
    const code128 = "12345678901234";
    const result = [...code128].reduce(appendDigit, "");
    expect(bufferToQuantity(result)).toBe(1);
  });

  it("ignores further digits once overflowed, and only a terminator clears it", () => {
    expect(appendDigit(OVERFLOW, "9")).toBe(OVERFLOW);
    expect(deleteDigit(OVERFLOW)).toBe("");
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

  it("treats the overflow sentinel as one", () => {
    expect(bufferToQuantity(OVERFLOW)).toBe(1);
  });
});
