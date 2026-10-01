import { describe, expect, it } from "vitest";
import { filterOptions, moveHighlight } from "./filterOptions";

const people = [
  { name: "DP-001", delivery_personnel: "KISII" },
  { name: "DP-002", delivery_personnel: "Kukena" },
  { name: "DP-003", delivery_personnel: "MIT CANTER" },
];
const label = (p: (typeof people)[number]) => p.delivery_personnel;

describe("filterOptions", () => {
  it("returns everything for an empty or blank query", () => {
    expect(filterOptions(people, "", label)).toEqual(people);
    expect(filterOptions(people, "   ", label)).toEqual(people);
  });

  it("matches anywhere in the label, ignoring case, keeping the order", () => {
    expect(filterOptions(people, "k", label).map(label)).toEqual(["KISII", "Kukena"]);
    expect(filterOptions(people, "can", label).map(label)).toEqual(["MIT CANTER"]);
  });

  it("matches the record's id too", () => {
    expect(filterOptions(people, "dp-002", label, (p) => p.name).map(label)).toEqual(["Kukena"]);
  });

  it("finds nothing for a query nothing contains", () => {
    expect(filterOptions(people, "zz", label)).toEqual([]);
  });
});

describe("moveHighlight", () => {
  it("steps within the list and wraps at both ends", () => {
    expect(moveHighlight(-1, 3, 1)).toBe(0);
    expect(moveHighlight(2, 3, 1)).toBe(0);
    expect(moveHighlight(0, 3, -1)).toBe(2);
  });

  it("has nothing to highlight in an empty list", () => {
    expect(moveHighlight(0, 0, 1)).toBe(-1);
  });
});
