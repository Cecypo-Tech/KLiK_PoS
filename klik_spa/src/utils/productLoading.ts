/**
 * Loading the till's product list and its category bar.
 *
 * The bar's groups come from their own small request and are kept between visits; the
 * item listing only sends groups while a search is narrowing them. Identical first-page
 * loads that overlap share one request instead of fetching the same 250 items twice.
 */

/** Placeholders only before the bar has any groups; every later reload keeps it on screen. */
export function showTabSkeleton(isLoading: boolean, isSearching: boolean, groupCount: number): boolean {
  return isLoading && !isSearching && groupCount === 0;
}

/** Group counts follow a search, so only a searching listing asks for them. */
export function listingIncludesGroups(searchQuery: string): boolean {
  return searchQuery.trim().length > 0;
}

/** Everything that changes a first page of the listing; equal keys mean an equal page. */
export function firstPageKey(context: {
  posName: string;
  customerId: string;
  priceList: string;
  warehouse: string | null | undefined;
  category: string;
  search: string;
}): string {
  return JSON.stringify([
    context.posName,
    context.customerId,
    context.priceList,
    context.warehouse || "",
    context.category,
    context.search.trim(),
  ]);
}

/** One in-flight request per key: a caller arriving with the same key gets that request. */
export function createKeyedDedupe<T>() {
  const inFlight = new Map<string, Promise<T>>();
  return (key: string, run: () => Promise<T>): Promise<T> => {
    const existing = inFlight.get(key);
    if (existing) return existing;
    const request = run().finally(() => {
      if (inFlight.get(key) === request) inFlight.delete(key);
    });
    inFlight.set(key, request);
    return request;
  };
}

/** A typed search asks for one short page: 50 rows are plenty to pick from while typing. */
export const SEARCH_PAGE_SIZE = 50;

/** The footer under a search's results - a search shows one page, so say when there are more. */
export function searchFooterLabel(shown: number, total: number): string {
  if (total > shown) {
    return `Showing the first ${shown} of ${total} matches - keep typing to narrow it down`;
  }
  return `${shown} ${shown === 1 ? "match" : "matches"}`;
}

/** Where the next page starts: the previous page's last row (see get_items' next_cursor). */
export interface PageCursor {
  after_name: string;
  after_code: string;
}

export interface PagePosition {
  cursor: PageCursor | null;
  offset: number;
}

/**
 * Whether a load-more actually moved forward. The grid's sentinel keeps firing while
 * hasMore is true, so a page that moved nothing must stop paging (see pagination.ts).
 * A server without cursors still advances by offset.
 */
export function pageAdvanced(before: PagePosition, after: PagePosition): boolean {
  if (after.cursor) {
    return (
      !before.cursor ||
      after.cursor.after_code !== before.cursor.after_code ||
      after.cursor.after_name !== before.cursor.after_name
    );
  }
  return after.offset > before.offset;
}

export interface ScrollNode {
  parentElement: ScrollNode | null;
}

/**
 * The element that actually scrolls the grid. The product list scrolls inside a container,
 * not the page; an IntersectionObserver rooted on the viewport sees the sentinel only once
 * the container shows it, so its margin could never prefetch. Null means the page scrolls.
 */
export function findScrollParent<T extends ScrollNode>(node: T, overflowY: (el: T) => string): T | null {
  let current = node.parentElement as T | null;
  while (current) {
    const value = overflowY(current);
    if (value === "auto" || value === "scroll") return current;
    current = current.parentElement as T | null;
  }
  return null;
}

/** Ask for the next page while the cashier is still two screens away from the end. */
export function prefetchRootMargin(viewportHeight: number): string {
  return `0px 0px ${Math.round(Math.max(viewportHeight, 400) * 2)}px 0px`;
}

/** Placeholder cards while a page loads: one grid row, or a few list rows. */
export function loadMoreSkeletonCount(isMobile: boolean, view: "grid" | "list"): number {
  if (view === "list") return 3;
  return isMobile ? 2 : 4;
}
