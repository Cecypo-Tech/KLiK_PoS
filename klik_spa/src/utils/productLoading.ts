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
