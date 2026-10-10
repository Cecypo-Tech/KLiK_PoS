import { describe, expect, it } from "vitest";
import { lineViewColumns } from "./lineViewColumns";

describe("lineViewColumns", () => {
  it("gives the item code its own column on wide screens when the till shows codes", () => {
    expect(lineViewColumns({ showItemCode: true, showCost: false })).toEqual({
      code: "hidden xl:flex xl:col-span-2",
      name: "col-span-6 xl:col-span-4",
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
