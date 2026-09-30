import { describe, expect, it } from "vitest";
import { stepValue } from "./stepValue";

describe("stepValue", () => {
  it("steps up and down by the step", () => {
    expect(stepValue(250, 1, 1)).toBe(251);
    expect(stepValue(250, -1, 1)).toBe(249);
  });

  it("starts from 0 on an empty field", () => {
    expect(stepValue("", 1, 1)).toBe(1);
  });

  it("never goes below the minimum", () => {
    expect(stepValue(0, -1, 1)).toBe(0);
    expect(stepValue(0.4, -1, 1, 0)).toBe(0);
  });

  it("does not leave float noise behind", () => {
    expect(stepValue(0.1, 1, 0.2)).toBe(0.3);
  });

  it("respects a maximum, e.g. a percentage", () => {
    expect(stepValue(100, 1, 1, 0, 100)).toBe(100);
  });
});
