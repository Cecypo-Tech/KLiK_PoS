/**
 * Whether the server left the sale for the background worker, from its own answer.
 *
 * The till's "Submit Invoice in Background" checkbox is only a request: a receipt-paid
 * M-Pesa sale, for one, is submitted at once. queue_status cannot tell either - it reads
 * "Queued" (its default) even on an invoice submitted directly.
 */
export function checkoutWasQueued(
  response: {
    checkout_status?: string;
    queue_status?: string | null;
    invoice?: { docstatus?: number | string; status?: string } | null;
  } | null | undefined,
): boolean {
  if (!response) return false;
  if (response.checkout_status) {
    return ["queued", "processing", "accepted"].includes(response.checkout_status);
  }
  const invoice = response.invoice;
  if (invoice?.docstatus !== undefined && invoice?.docstatus !== null) return Number(invoice.docstatus) === 0;
  if (invoice?.status) return invoice.status === "Draft";
  return Boolean(response.queue_status);
}
