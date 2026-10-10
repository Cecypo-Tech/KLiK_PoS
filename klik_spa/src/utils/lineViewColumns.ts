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

// ponytail: ERPNext's default root name; a site that renamed its root shows it, harmlessly.
const ROOT_ITEM_GROUP = "All Item Groups";

/** The item's group, shown beside its name only when it tells the cashier something: never the
 * root group, nor the group the selected tab already names ("all" is the All Items tab). */
export function groupLabel(category: string | undefined, selectedCategory: string): string | null {
  if (!category || category === ROOT_ITEM_GROUP || category === selectedCategory) return null;
  return category;
}
