/**
 * A returning walk-in gives only their phone number: their name and PIN come back from their
 * last sales (klik_pos.api.customer.get_walkin_details_by_phone), into the fields the cashier
 * left blank - never over what they typed.
 */

export interface RecalledWalkin {
  name?: string;
  tax_id?: string;
}

/** Enough of a number to look up: the server matches on its last 9 digits. */
export function recallablePhone(phone: string): boolean {
  return phone.replace(/\D/g, "").length >= 9;
}

export function withRecalled(
  current: { name: string; taxId: string },
  found: RecalledWalkin,
): { name: string; taxId: string } {
  return {
    name: current.name.trim() ? current.name : found.name || current.name,
    taxId: current.taxId.trim() ? current.taxId : found.tax_id || current.taxId,
  };
}

export async function fetchRecalledWalkin(phone: string): Promise<RecalledWalkin> {
  const res = await fetch(
    `/api/method/klik_pos.api.customer.get_walkin_details_by_phone?phone=${encodeURIComponent(phone)}`,
    { credentials: "include" },
  );
  return ((await res.json())?.message || {}) as RecalledWalkin;
}
