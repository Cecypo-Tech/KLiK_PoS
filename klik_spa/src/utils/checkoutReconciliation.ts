/**
 * The receipt prints its lines from the cart and its totals from the server's preview
 * invoice. When those two disagree the customer is handed a receipt whose lines do not
 * add up to its own total, and is charged the server's number. This compares them so
 * the checkout can stop instead.
 */

export interface PreviewLine {
  item_code: string;
  qty: number;
  rate: number;
  amount: number;
}

export interface CartLine {
  item_code: string;
  qty: number;
  rate: number;
}

export interface ExtraCharge {
  item_code: string;
  amount: number;
}

export interface Reconciliation {
  /** False means: do not take money and do not print. */
  ok: boolean;
  /** Cashier-facing explanation, or null when everything lines up. */
  message: string | null;
  /** Lines the server added that the cart never had - a delivery charge, say. */
  extraCharges: ExtraCharge[];
}

const DEFAULT_EPSILON = 0.01;

function format(value: number) {
  return Number(value.toFixed(2)).toString();
}

export function reconcileCheckout(
  cartLines: CartLine[],
  previewLines: PreviewLine[],
  epsilon: number = DEFAULT_EPSILON,
): Reconciliation {
  const previewByCode = new Map<string, PreviewLine>();
  for (const line of previewLines) {
    previewByCode.set(line.item_code, line);
  }

  for (const cartLine of cartLines) {
    const previewLine = previewByCode.get(cartLine.item_code);

    if (!previewLine) {
      return {
        ok: false,
        message: `${cartLine.item_code} is in the cart but not on the invoice the server priced. Reopen the cart and try again.`,
        extraCharges: [],
      };
    }

    if (Math.abs(previewLine.rate - cartLine.rate) > epsilon) {
      return {
        ok: false,
        message: `Price mismatch on ${cartLine.item_code}: this till has ${format(cartLine.rate)} and the server priced it at ${format(previewLine.rate)}. Check the item's price list and any Pricing Rule for this customer before selling.`,
        extraCharges: [],
      };
    }

    if (Math.abs(previewLine.qty - cartLine.qty) > epsilon) {
      return {
        ok: false,
        message: `Quantity mismatch on ${cartLine.item_code}: this till has ${format(cartLine.qty)} and the server priced ${format(previewLine.qty)}.`,
        extraCharges: [],
      };
    }
  }

  const cartCodes = new Set(cartLines.map((line) => line.item_code));
  const extraCharges = previewLines
    .filter((line) => !cartCodes.has(line.item_code))
    .map((line) => ({ item_code: line.item_code, amount: line.amount }));

  return { ok: true, message: null, extraCharges };
}
