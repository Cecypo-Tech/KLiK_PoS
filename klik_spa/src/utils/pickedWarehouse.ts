/**
 * The warehouse a cashier picked, kept apart from the till's cached details: those are
 * refetched on every window focus and cleared on unload, while the cart - filled from the
 * pick - survives both. Losing the pick then would sell the cart from the till's own stock.
 */
export type KeptPick = { profile: string; user: string; warehouse: string };

const KEY = "klik-picked-warehouse";

type Till = { name?: string; warehouse?: string; allow_warehouse_change?: boolean | number } | null | undefined;

/** The till's warehouse after its details load: the kept pick if it is still this till's and user's. */
export function warehouseAfterLoad(till: Till, user: string | undefined, kept: KeptPick | null): string | null {
  const own = till?.warehouse || null;
  if (!kept || !till?.allow_warehouse_change || kept.profile !== till.name || kept.user !== user) return own;
  return kept.warehouse;
}

export function readPick(): KeptPick | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "null");
  } catch {
    return null;
  }
}

/** Remember `warehouse` for this till and user; the till's own (or none) forgets the pick. */
export function keepPick(till: Till, user: string | undefined, warehouse: string | null) {
  try {
    if (!warehouse || !till?.name || !user || warehouse === till.warehouse) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, JSON.stringify({ profile: till.name, user, warehouse }));
  } catch {
    // Private mode / blocked storage: the pick lasts until the next refresh, as before.
  }
}
