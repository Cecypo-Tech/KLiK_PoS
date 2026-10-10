import { describe, expect, it } from "vitest";
import { groupLabel, lineViewColumns } from "./lineViewColumns";

describe("lineViewColumns", () => {
  it("gives the item code its own column on wide screens when the till shows codes", () => {
    expect(lineViewColumns({ showItemCode: true, showCost: false })).toEqual({
      code: "hidden xl:flex xl:col-span-3",
      name: "col-span-6 xl:col-span-3",
    });
  });

  it("makes room for the cost column", () => {
    expect(lineViewColumns({ showItemCode: true, showCost: true })).toEqual({
      code: "hidden xl:flex xl:col-span-2",
      name: "col-span-5 xl:col-span-3",
    });
  });

  it("drops the code column when the till hides codes", () => {
    expect(lineViewColumns({ showItemCode: false, showCost: false })).toEqual({ code: null, name: "col-span-6" });
    expect(lineViewColumns({ showItemCode: false, showCost: true })).toEqual({ code: null, name: "col-span-5" });
  });
});

describe("groupLabel", () => {
  it("names the item's group on All Items and in search", () => {
    expect(groupLabel("Brake Pads", "all")).toBe("Brake Pads");
  });

  it("says nothing for the root group", () => {
    expect(groupLabel("All Item Groups", "all")).toBeNull();
  });

  it("says nothing when the selected tab already names it", () => {
    expect(groupLabel("Brake Pads", "Brake Pads")).toBeNull();
  });

  it("names a sub-group under its parent's tab", () => {
    expect(groupLabel("Front Pads", "Brake Pads")).toBe("Front Pads");
  });

  it("says nothing for an item with no group", () => {
    expect(groupLabel(undefined, "all")).toBeNull();
  });
});
