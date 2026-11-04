const csrf = () => (window as { csrf_token?: string }).csrf_token as string;

const serverMessage = (result: { _server_messages?: string } | null) => {
  try {
    return JSON.parse(JSON.parse(result?._server_messages || "[]")[0]).message as string | undefined;
  } catch {
    return undefined;
  }
};

/** Save the cart as a submitted Quotation; takes the held-order payload. Never throws. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function createQuote(data: any): Promise<{ success: boolean; quote_name?: string; message?: string }> {
  try {
    const response = await fetch("/api/method/klik_pos.api.quotation.create_quote", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf() },
      body: JSON.stringify({ data }),
      credentials: "include",
    });
    const result = await response.json().catch(() => null);
    if (response.ok && result?.message?.success) return result.message;
    return {
      success: false,
      message: result?.message?.message || serverMessage(result) || "Failed to save the quote",
    };
  } catch (error) {
    return { success: false, message: error instanceof Error ? error.message : "Failed to save the quote" };
  }
}

export interface QuoteListRow {
  name: string;
  customer: string;
  customer_name: string;
  walkin_name: string | null;
  transaction_date: string;
  valid_till: string | null;
  grand_total: number;
  currency: string;
  expired: boolean;
}

export async function getQuotes(params: { limit?: number; start?: number; search?: string } = {}) {
  const qs = new URLSearchParams({
    limit: String(params.limit ?? 50),
    start: String(params.start ?? 0),
    search: params.search ?? "",
  }).toString();
  const response = await fetch(`/api/method/klik_pos.api.quotation.get_quotes?${qs}`, { credentials: "include" });
  const result = await response.json();
  return result.message as { success: boolean; data?: QuoteListRow[]; message?: string };
}

/** Same shape as getHeldOrderDetails, plus whether the quote is past its valid-till date. */
export async function getQuoteDetails(quoteId: string) {
  const response = await fetch(
    `/api/method/klik_pos.api.quotation.get_quote_details?quote_id=${encodeURIComponent(quoteId)}`,
    { credentials: "include" },
  );
  const result = await response.json();
  return result.message as {
    success: boolean;
    name: string;
    customer: string;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    customer_data?: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    items: any[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    cart_meta: any;
    grand_total: number;
    currency: string;
    expired: boolean;
    message?: string;
  };
}
