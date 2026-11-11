/**
 * Column template shared by the cart's header row (OrderSummary) and every cart line
 * (CartItemRow), so the two stay aligned: Item | Qty | Rate | Total.
 */
export const CART_ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_7.5rem_4.5rem_5.75rem] @max-[20rem]:grid-cols-[minmax(0,1fr)_7.5rem_5.75rem] items-center gap-x-2";
// The @max-[20rem] form applies only inside an @container narrower than 20rem: the grid till's
// side panel below 1280 px (OrderSummary), where the per-unit rate drops out (CartItemRow).
