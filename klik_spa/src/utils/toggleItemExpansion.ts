/**
 * Toggles which cart line's details panel is open. At most one at a time:
 * opening a different line closes whichever was open, and re-toggling the
 * currently-open line closes it.
 */
export function nextExpandedCartItemId(current: string | null, id: string): string | null {
  return current === id ? null : id;
}
