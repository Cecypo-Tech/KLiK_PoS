/**
 * Whether "Switch profile" is offered, and why it can't be used right now. Leaving
 * (klik_pos.api.shift.leave_shift) keeps the shift open for whoever is still in it, or a
 * manager, to close - so an opener may leave too. A cashier with one profile, or in no
 * shift, is not offered it. The page reloads to switch, so a cart in progress must be held.
 */
export function switchProfileState({
  profileCount,
  shift,
  cartCount,
}: {
  profileCount: number;
  shift: { entry?: string | null } | null;
  cartCount: number;
}): { show: boolean; blocked: string | null } {
  if (profileCount < 2 || !shift?.entry) return { show: false, blocked: null };
  if (cartCount > 0) return { show: true, blocked: "Hold or clear the cart first" };
  return { show: true, blocked: null };
}
