/**
 * The draft Sales Order an M-Pesa STK push is sent from (klik_pos.api.mpesa_order). It stands
 * in for the sale until the cashier submits: no invoice exists for a push that is never paid.
 */
import type { KeptMpesaPush } from '../utils/mpesaDraftLifecycle';
import { HeldOrderGoneError } from './salesOrder';

/** The newest push sent from an M-Pesa order, as get_held_order_details returns it. */
export type MpesaPushInfo = KeptMpesaPush;

const csrf = () => (window as { csrf_token?: string }).csrf_token as string;

async function post(method: string, body: object) {
  const response = await fetch(`/api/method/klik_pos.api.mpesa_order.${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf() },
    body: JSON.stringify(body),
    credentials: 'include',
  });
  const result = await response.json();
  if (result.message?.code === 'held_order_gone') {
    throw new HeldOrderGoneError(result.message.message, result.message.order_id);
  }
  if (!response.ok || !result.message || result.message.success === false) {
    const msg = result.message?.message || result.message?.error || result._server_messages || 'Request failed';
    throw new Error(msg);
  }
  return result.message;
}

/** Create the order a push is sent from, or bring `orderId` up to this cart. Its name. */
export async function saveMpesaOrder(data: Record<string, unknown>, orderId?: string | null): Promise<string> {
  const result = await post('save_mpesa_order', { data: { ...data, ...(orderId ? { mpesa_order_id: orderId } : {}) } });
  return result.order_name as string;
}

/**
 * The cashier left checkout unfinished. kept: a push sent from the order may still pay it (or
 * did), so the server kept it as a held order instead of deleting it.
 */
export async function discardMpesaOrder(orderId: string): Promise<{ kept: false } | { kept: true; message: string }> {
  const result = await post('discard_mpesa_order', { order_id: orderId });
  return result.kept ? { kept: true, message: result.message } : { kept: false };
}

/** Turn the order into the submitted (or queued) Sales Invoice; same reply as submitDraftInvoice. */
export async function submitMpesaOrder(
  orderId: string,
  data: unknown,
  heldOrderId: string | null,
  remarks: string,
) {
  return post('submit_mpesa_order', {
    order_id: orderId,
    data,
    ...(heldOrderId ? { held_order_id: heldOrderId } : {}),
    remarks,
  });
}
