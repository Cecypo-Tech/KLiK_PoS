/**
 * KRA PIN -> taxpayer name (klik_pos.api.tax_pin.lookup_tax_pin), fired as the PIN is typed:
 * once the whole PIN is in (letter, 9 digits, letter), and only once per PIN.
 */

/** The PIN to look up now, or null while it is incomplete or was just looked up. */
export function pinToLookUp(value: string, lastLookedUp: string): string | null {
  const pin = value.trim().toUpperCase();
  return /^[A-Z]\d{9}[A-Z]$/.test(pin) && pin !== lastLookedUp ? pin : null;
}

export async function lookupTaxPin(pin: string): Promise<{ success?: boolean; name?: string; message?: string }> {
  const res = await fetch(
    `/api/method/klik_pos.api.tax_pin.lookup_tax_pin?pin=${encodeURIComponent(pin)}`,
    { credentials: "include" },
  );
  return (await res.json())?.message || {};
}
