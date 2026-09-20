/**
 * Which identifier to show as an item's primary label: the item name, or the item code
 * when the POS Profile's "Show Item Code Instead Of Item Name" toggle is on. Distinct from
 * custom_show_item_code_in_product_list, which adds the code as a secondary subtitle
 * alongside the name rather than replacing it.
 */
export function getItemDisplayName(
  item: { name?: string; item_name?: string; item_code?: string; id?: string },
  useItemCodeAsName?: boolean
): string {
  const name = item.name || item.item_name || "";
  if (!useItemCodeAsName) return name;
  return item.item_code || item.id || name;
}
