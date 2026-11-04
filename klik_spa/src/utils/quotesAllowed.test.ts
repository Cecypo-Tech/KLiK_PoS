import { describe, expect, it } from "vitest";
import { quotesAllowed } from "./quotesAllowed";

describe("quotesAllowed", () => {
  it("is on unless the till switches it off", () => {
    expect(quotesAllowed(undefined)).toBe(true);
    expect(quotesAllowed({})).toBe(true);
    expect(quotesAllowed({ custom_allow_quotes: 1 })).toBe(true);
    expect(quotesAllowed({ custom_allow_quotes: 0 })).toBe(false);
    expect(quotesAllowed({ custom_allow_quotes: "0" })).toBe(false);
    expect(quotesAllowed({ custom_allow_quotes: false })).toBe(false);
  });
});
