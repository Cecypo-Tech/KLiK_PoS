import { describe, expect, it } from "vitest";
import { groupHeaders, lineViewColumns } from "./lineViewColumns";

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

describe("groupHeaders", () => {
  const browsing = { searching: false, selectedCategory: "all" };

  it("heads the first item of each group", () => {
    expect(groupHeaders(["Brakes", "Brakes", "Filters", "Oils"], browsing)).toEqual(
      new Map([[0, "Brakes"], [2, "Filters"], [3, "Oils"]]),
    );
  });

  it("heads nothing while searching: results stay in best-match order", () => {
    expect(groupHeaders(["Brakes", "Filters"], { searching: true, selectedCategory: "all" }).size).toBe(0);
  });

  it("heads nothing when the tab already names the only group", () => {
    expect(groupHeaders(["Brakes", "Brakes"], { searching: false, selectedCategory: "Brakes" }).size).toBe(0);
  });

  it("heads each sub-group under its parent's tab", () => {
    expect(groupHeaders(["Front Pads", "Rear Pads"], { searching: false, selectedCategory: "Brakes" })).toEqual(
      new Map([[0, "Front Pads"], [1, "Rear Pads"]]),
    );
  });

  it("heads an item with no group as Ungrouped", () => {
    expect(groupHeaders([undefined], browsing)).toEqual(new Map([[0, "Ungrouped"]]));
  });
});
