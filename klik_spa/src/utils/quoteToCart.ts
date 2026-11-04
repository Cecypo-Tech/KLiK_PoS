import { toast } from 'react-toastify';
import { getQuoteDetails } from '../services/quotation';
import { useCartStore } from '../stores/cartStore';
import { cacheQuote } from './draftInvoiceCache';
import { fillCartFromOrder } from './heldOrderToCart';

/** Load a saved quote into the cart as a sale. On a refusal it says why and leaves the cart. */
export async function addQuoteToCart(quoteId: string): Promise<boolean> {
  const details = await getQuoteDetails(quoteId);
  if (!details?.success) {
    toast.error(details?.message || 'Failed to load the quote');
    return false;
  }

  // Loading a quote is selling it: back to normal stock rules.
  useCartStore.getState().exitQuoteMode();
  const loaded = await fillCartFromOrder(details, (items, customer) =>
    cacheQuote(quoteId, items, customer, Number((details as { discount_amount?: number }).discount_amount) || 0),
  );

  if (loaded && details.expired) {
    await useCartStore.getState().refreshCartPricing();
    toast.info("Quote expired - re-priced at today's prices");
  }
  return loaded;
}
