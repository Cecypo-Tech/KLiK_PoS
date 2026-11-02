/**
 * Minimum selling price = the price list at a till that enforces it (cecypo_powerpack).
 *
 * Checkout's preview (validate_checkout_invoice) returns `price_floor`: the lines priced below
 * their list. The sale cannot complete until each is fixed or a supervisor authorises it with
 * their PIN; the server checks the authorisation again when the invoice is saved.
 */

export interface FloorRow {
  idx: number;
  item_code: string;
  item_name: string;
  uom: string | null;
  qty: number;
  rate: number;
  minimum: number;
  price_list: string;
}

export interface PriceFloor {
  enforced: boolean;
  rows: FloorRow[];
}

export interface FloorAuthorisation {
  token: string;
  /** floorRowsKey of the lines the supervisor saw. */
  key: string;
  supervisorName?: string;
}

/** The cart's price list for checkout and holds, when the till lets the cashier pick one. */
export function checkoutPriceList(
  posDetails: { allow_price_list_switching?: unknown } | null | undefined,
  selectedPriceList: string | null | undefined,
): string | null {
  const allowed = Boolean(Number(posDetails?.allow_price_list_switching ?? 0));
  return allowed && selectedPriceList ? selectedPriceList : null;
}

export function floorRowsKey(rows: FloorRow[]): string {
  return JSON.stringify(
    rows
      .map((r) => [r.item_code, r.uom ?? "", Number(r.qty), Number(r.rate)])
      .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
  );
}

/** A supervisor authorised these exact lines; any change to them needs a new authorisation. */
export function authorisationStillValid(auth: FloorAuthorisation | null, rows: FloorRow[]): boolean {
  return Boolean(auth) && auth!.key === floorRowsKey(rows);
}

/** Why payment is blocked by the minimum price, or null. */
export function floorBlockMessage(floor: PriceFloor | null | undefined, auth: FloorAuthorisation | null): string | null {
  if (!floor?.rows?.length) return null;
  if (authorisationStillValid(auth, floor.rows)) return null;
  return "Prices below the minimum - fix them or ask a supervisor to authorise";
}
