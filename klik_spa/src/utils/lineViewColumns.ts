/**
 * The list view's code and name columns, of the 12-column grid. On wide screens (xl) the item
 * code gets a column of its own when the till shows codes; below xl it stays under the name.
 * Class names are written out whole so Tailwind keeps them.
 */
export function lineViewColumns({ showItemCode, showCost }: { showItemCode: boolean; showCost: boolean }) {
  const name = showCost ? "col-span-5" : "col-span-6";
  if (!showItemCode) return { code: null, name };
  // The code column also holds the thumbnail: without the cost column it takes 3.
  return showCost
    ? { code: "hidden xl:flex xl:col-span-2", name: `${name} xl:col-span-3` }
    : { code: "hidden xl:flex xl:col-span-3", name: `${name} xl:col-span-3` };
}

/** Where the list view heads a group: index of each group's first item -> its name. The
 * listing comes group by group while browsing; a search is ranked, so it gets no headers, and
 * nor does a tab whose own group is all there is. */
export function groupHeaders(
  categories: Array<string | undefined>,
  { searching, selectedCategory }: { searching: boolean; selectedCategory: string },
): Map<number, string> {
  const headers = new Map<number, string>();
  if (searching) return headers;
  let previous: string | null = null;
  categories.forEach((category, index) => {
    const group = category || "Ungrouped";
    if (group !== previous) headers.set(index, group);
    previous = group;
  });
  if (headers.size === 1 && headers.get(0) === selectedCategory) headers.clear();
  return headers;
}
