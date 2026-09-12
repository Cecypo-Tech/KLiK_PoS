/**
 * What a discount took off a receipt line.
 *
 * The cart shows a discounted line twice over: the list amount struck through, the
 * amount actually charged beneath it, and a "Discount" row in the footer. The printed
 * receipt showed none of that - just the discounted line - so a customer looking at a
 * rule-discounted sale could not see the discount they had been given, and the cart and
 * the receipt disagreed about whether one existed.
 */

import { roundCurrency } from "./currencyMath";

export interface DiscountableLine {
  quantity: number;
  /** The price-list rate, before any per-item or rule discount. */
  listRate: number;
  /** What the line is actually being charged at. */
  sellRate: number;
}

export function getLineDiscount({ quantity, listRate, sellRate }: DiscountableLine): number {
  // A line with no list rate is not a 100% discount - it is a line we know nothing about.
  if (!listRate) return 0;
  const perUnit = listRate - sellRate;
  if (perUnit <= 0) return 0;
  return roundCurrency(perUnit * quantity);
}

export function getItemDiscountTotal(lines: DiscountableLine[]): number {
  return roundCurrency(lines.reduce((sum, line) => sum + getLineDiscount(line), 0));
}
