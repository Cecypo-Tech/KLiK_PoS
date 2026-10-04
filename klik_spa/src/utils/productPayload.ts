import type { ItemTaxInfo, MenuItem } from "../../types";

type WireItem = MenuItem & { tax_key?: string };

/**
 * A compact listing page sends each tax profile once and a `tax_key` per item; put the
 * profile back on every item so components keep reading `item.tax_info`. Items sharing a
 * profile share one object.
 */
export function expandTaxProfiles(
  items: WireItem[],
  profiles: Record<string, ItemTaxInfo> | undefined,
): MenuItem[] {
  if (!profiles) return items;
  return items.map((item) => {
    if (!item.tax_key) return item;
    const expanded: WireItem = { ...item, tax_info: profiles[item.tax_key] };
    delete expanded.tax_key;
    return expanded;
  });
}
