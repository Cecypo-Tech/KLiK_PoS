/**
 * The list view's code and name columns, of the 12-column grid. On wide screens (xl) the item
 * code gets a column of its own when the till shows codes; below xl it stays under the name.
 * Class names are written out whole so Tailwind keeps them.
 */
export function lineViewColumns({ showItemCode, showCost }: { showItemCode: boolean; showCost: boolean }) {
  const name = showCost ? "col-span-5" : "col-span-6";
  if (!showItemCode) return { code: null, name };
  return { code: "hidden xl:flex xl:col-span-2", name: `${name} ${showCost ? "xl:col-span-3" : "xl:col-span-4"}` };
}
