/**
 * Clear Cart on a cart resumed from a held order discards that order too - cleared, it used
 * to stay on the Held tab, a copy of a sale the cashier had thrown away.
 *
 * Returns why the cart must stay (the server refused: an M-Pesa request sent from the order
 * may still pay it), or null when the cart may clear.
 */
export async function discardHeldOrder(
  orderId: string | null,
  deleteOrder: (orderId: string) => Promise<unknown>,
): Promise<string | null> {
  if (!orderId) return null;
  try {
    await deleteOrder(orderId);
    return null;
  } catch (err) {
    // Checked out or cleared elsewhere: nothing left to discard.
    if (err instanceof Error && err.name === "HeldOrderGoneError") return null;
    return err instanceof Error && err.message ? err.message : "Could not delete the held order.";
  }
}
