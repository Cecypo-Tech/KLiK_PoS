/**
 * Whether the user menu offers "Switch profile", and why it can't be used right now.
 * Leaving only works on a shift the cashier joined (klik_pos.api.shift.leave_shift); the
 * opener has to close theirs. A cashier with one profile is never offered it: there is
 * nowhere to switch to. The page reloads to switch, so a cart in progress must be held first.
 */
export function switchProfileState({
  profileCount,
  shift,
  cartCount,
}: {
  profileCount: number;
  shift: { joined?: boolean } | null;
  cartCount: number;
}): { show: boolean; blocked: string | null } {
  if (profileCount < 2 || !shift) return { show: false, blocked: null };
  if (!shift.joined) return { show: true, blocked: "Close this shift to switch" };
  if (cartCount > 0) return { show: true, blocked: "Hold or clear the cart first" };
  return { show: true, blocked: null };
}
