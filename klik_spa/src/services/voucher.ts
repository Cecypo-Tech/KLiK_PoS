import type { Customer } from "../types/customer";
import { transformCustomerInfo } from "../utils/transformCustomerInfo";
import type { VoucherLookup } from "../utils/voucher";

/** What a store-credit voucher holds, by its credit note number plus the original sale's. */
export async function lookupCreditVoucher(creditNote: string, originalInvoice: string): Promise<VoucherLookup> {
  const params = new URLSearchParams({ credit_note: creditNote, original_invoice: originalInvoice });
  const response = await fetch(`/api/method/klik_pos.api.customer_credit.lookup_credit_voucher?${params.toString()}`, {
    credentials: "include",
  });
  if (response.status === 429) {
    throw new Error("Too many voucher checks - wait a minute and try again.");
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.message) {
    throw new Error(`Could not check the voucher (server answered ${response.status})`);
  }
  return result.message as VoucherLookup;
}

/** The full customer record, to switch a sale to a voucher's owner. Null when it can't load. */
export async function fetchCustomerRecord(customerName: string): Promise<Customer | null> {
  try {
    const response = await fetch(
      `/api/method/klik_pos.api.customer.get_customer_info?customer_name=${encodeURIComponent(customerName)}`,
      { credentials: "include" },
    );
    const data = await response.json().catch(() => ({}));
    if (!data.message || data.message.success === false) return null;
    return transformCustomerInfo(data.message, "");
  } catch {
    return null;
  }
}
