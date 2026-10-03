import { describe, expect, it } from "vitest";
import { createKeyedDedupe, firstPageKey, listingIncludesGroups, showTabSkeleton } from "./productLoading";

describe("showTabSkeleton", () => {
  it("shows placeholders while the first load has no groups to show", () => {
    expect(showTabSkeleton(true, false, 0)).toBe(true);
  });

  it("keeps the bar on screen through every later reload", () => {
    expect(showTabSkeleton(true, false, 14)).toBe(false);
  });

  it("never covers the bar for a search", () => {
    expect(showTabSkeleton(true, true, 0)).toBe(false);
  });
});

describe("listingIncludesGroups", () => {
  it("asks the listing for groups only while a search narrows them", () => {
    expect(listingIncludesGroups("brake pad")).toBe(true);
    expect(listingIncludesGroups("")).toBe(false);
    expect(listingIncludesGroups("   ")).toBe(false);
  });
});

describe("firstPageKey", () => {
  const base = {
    posName: "Main Till",
    customerId: "CRN TEST",
    priceList: "Standard Selling",
    warehouse: "Stores - DC",
    category: "all",
    search: "",
  };

  it("is the same for the same context", () => {
    expect(firstPageKey(base)).toBe(firstPageKey({ ...base }));
  });

  it("differs when anything that changes the page changes", () => {
    expect(firstPageKey(base)).not.toBe(firstPageKey({ ...base, category: "Brakes" }));
    expect(firstPageKey(base)).not.toBe(firstPageKey({ ...base, customerId: "Walk In" }));
    expect(firstPageKey(base)).not.toBe(firstPageKey({ ...base, priceList: "Wholesale" }));
  });
});

describe("createKeyedDedupe", () => {
  it("gives a second caller with the same key the first one's request", async () => {
    const dedupe = createKeyedDedupe<number>();
    let calls = 0;
    const run = () => {
      calls += 1;
      return new Promise<number>((resolve) => setTimeout(() => resolve(42), 5));
    };
    const [a, b] = await Promise.all([dedupe("k", run), dedupe("k", run)]);
    expect([a, b, calls]).toEqual([42, 42, 1]);
  });

  it("runs again once the first request has settled", async () => {
    const dedupe = createKeyedDedupe<number>();
    let calls = 0;
    const run = async () => {
      calls += 1;
      return calls;
    };
    await dedupe("k", run);
    await dedupe("k", run);
    expect(calls).toBe(2);
  });

  it("does not share between different keys", async () => {
    const dedupe = createKeyedDedupe<string>();
    const results = await Promise.all([dedupe("a", async () => "a"), dedupe("b", async () => "b")]);
    expect(results).toEqual(["a", "b"]);
  });

  it("forgets a failed request so the next caller retries", async () => {
    const dedupe = createKeyedDedupe<number>();
    await expect(dedupe("k", async () => Promise.reject(new Error("offline")))).rejects.toThrow("offline");
    await expect(dedupe("k", async () => 7)).resolves.toBe(7);
  });
});
