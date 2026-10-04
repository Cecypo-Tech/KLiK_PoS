import { describe, expect, it } from "vitest";
import {
  createKeyedDedupe,
  findScrollParent,
  firstPageKey,
  listingIncludesGroups,
  loadMoreSkeletonCount,
  pageAdvanced,
  prefetchRootMargin,
  showTabSkeleton,
  SEARCH_PAGE_SIZE,
  searchFooterLabel,
} from "./productLoading";

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

describe("searchFooterLabel", () => {
  it("says when a search shows only its first page", () => {
    expect(searchFooterLabel(50, 120)).toBe("Showing the first 50 of 120 matches - keep typing to narrow it down");
  });

  it("counts the matches when they all fit", () => {
    expect(searchFooterLabel(7, 7)).toBe("7 matches");
    expect(searchFooterLabel(1, 1)).toBe("1 match");
  });

  it("asks the server for one short page", () => {
    expect(SEARCH_PAGE_SIZE).toBe(50);
  });
});

describe("pageAdvanced", () => {
  const cursor = (code: string) => ({ after_name: code, after_code: code });

  it("counts a new cursor as progress", () => {
    expect(pageAdvanced({ cursor: cursor("A"), offset: 0 }, { cursor: cursor("B"), offset: 0 })).toBe(true);
  });

  it("does not count the same cursor twice", () => {
    expect(pageAdvanced({ cursor: cursor("A"), offset: 3 }, { cursor: cursor("A"), offset: 3 })).toBe(false);
  });

  it("falls back to the offset against a server without cursors", () => {
    expect(pageAdvanced({ cursor: null, offset: 150 }, { cursor: null, offset: 300 })).toBe(true);
    expect(pageAdvanced({ cursor: null, offset: 150 }, { cursor: null, offset: 150 })).toBe(false);
  });
});

describe("findScrollParent", () => {
  type Box = { name: string; overflowY: string; parentElement: Box | null };
  const node = (name: string, overflowY: string, parentElement: Box | null): Box => ({ name, overflowY, parentElement });

  it("finds the nearest scrolling ancestor", () => {
    const page = node("page", "visible", null);
    const scroller = node("scroller", "auto", page);
    const grid = node("grid", "visible", scroller);
    const sentinel = node("sentinel", "visible", grid);
    expect(findScrollParent(sentinel, (el) => el.overflowY)?.name).toBe("scroller");
  });

  it("returns null when only the page scrolls", () => {
    const sentinel = node("sentinel", "visible", node("page", "visible", null));
    expect(findScrollParent(sentinel, (el) => el.overflowY)).toBeNull();
  });
});

describe("prefetchRootMargin", () => {
  it("reaches two screens below what is visible", () => {
    expect(prefetchRootMargin(700)).toBe("0px 0px 1400px 0px");
  });

  it("never shrinks below two 400px screens", () => {
    expect(prefetchRootMargin(0)).toBe("0px 0px 800px 0px");
  });
});

describe("loadMoreSkeletonCount", () => {
  it("fills one row of the grid, or a few list rows", () => {
    expect(loadMoreSkeletonCount(false, "grid")).toBe(4);
    expect(loadMoreSkeletonCount(true, "grid")).toBe(2);
    expect(loadMoreSkeletonCount(false, "list")).toBe(3);
  });
});
