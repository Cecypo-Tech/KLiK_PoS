export interface ReturnItem {
  item_code: string;
  item_name: string;
  qty: number;
  rate: number;
  amount: number;
  returned_qty: number;
  available_qty: number;
  return_qty?: number;
}

/** A fixed ("Actual") charge on the sale - a Shipping Rule's courier fee. A line the
 * cashier ticks, like an item. `reversed_by` names the credit note that already took it
 * back; `return_charge` is the cashier's tick, undefined until touched. */
export interface FixedCharge {
  description: string;
  account_head: string;
  amount: number;
  reversed_by: string | null;
  return_charge?: boolean;
}

export interface InvoiceForReturn {
  name: string;
  posting_date: string;
  posting_time: string;
  customer: string;
  grand_total: number;
  paid_amount?: number;
  status: string;
  items: ReturnItem[];
  fixed_charges?: FixedCharge[];
}

export interface ReturnData {
  customer: string;
  invoice_returns: {
    invoice_name: string;
    return_items: ReturnItem[];
    payment_method?: string;
    return_amount?: number;
    /** 1 reverses the sale's fixed charges on the credit note, 0 leaves them off. */
    return_fixed_charges?: 0 | 1;
  }[];
}

export async function getReturnedQty(customer: string, salesInvoice: string, item: string) {
  const csrfToken = window.csrf_token
  try {
    const response = await fetch(`/api/method/klik_pos.api.sales_invoice.returned_qty`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken
      },
      body: JSON.stringify({
        customer,
        sales_invoice: salesInvoice,
        item
      }),
       credentials: 'include'
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || 'Failed to get returned quantity');
    }

    return {
      success: true,
      data: data.message
    };
          //eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    console.error('Error getting returned quantity:', error);
    return {
      success: false,
      error: error.message || 'Failed to get returned quantity'
    };
  }
}

export async function getCustomerInvoicesForReturn(
  customer: string,
  startDate?: string,
  endDate?: string,
  shippingAddress?: string
): Promise<{success: boolean; data?: InvoiceForReturn[]; error?: string}> {
  try {
    const params = new URLSearchParams({
      customer,
      ...(startDate && { start_date: startDate }),
      ...(endDate && { end_date: endDate }),
      ...(shippingAddress && { shipping_address: shippingAddress })
    });

    const response = await fetch(`/api/method/klik_pos.api.sales_invoice.get_customer_invoices_for_return?${params}`);
    const data = await response.json();

    if (!response.ok || !data.message.success) {
      throw new Error(data.message.error || 'Failed to fetch customer invoices');
    }

    return {
      success: true,
      data: data.message.data
    };
          //eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    console.error('Error fetching customer invoices for return:', error);
    return {
      success: false,
      error: error.message || 'Failed to fetch customer invoices'
    };
  }
}

export async function createPartialReturn(
  invoiceName: string,
  returnItems: ReturnItem[],
  paymentMethod?: string,
  returnAmount?: number,
  returnFixedCharges?: 0 | 1
): Promise<{success: boolean; returnInvoice?: string; message?: string; error?: string}> {

  const csrfToken = window.csrf_token;
  try {
    const response = await fetch(`/api/method/klik_pos.api.sales_invoice.create_partial_return`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken
      },
      body: JSON.stringify({
        invoice_name: invoiceName,
        return_items: returnItems,
        payment_method: paymentMethod || 'Cash',
        return_amount: returnAmount || 0,
        // The courier fee is the cashier's call, like an item: 1 reverses it, 0 leaves it off.
        ...(returnFixedCharges === undefined ? {} : { return_fixed_charges: returnFixedCharges })
      }),
       credentials: 'include'
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || 'Failed to create partial return');
    }

    // Handle both response formats
    const result = data.message || data;

    if (!result.success) {
      throw new Error(result.message || 'Failed to create partial return');
    }

    return {
      success: true,
      returnInvoice: result.return_invoice,
      message: result.message
    };
        //eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    console.error('Error creating partial return:', error);
    return {
      success: false,
      error: error.message || 'Failed to create partial return'
    };
  }
}

export async function createMultiInvoiceReturn(
  returnData: ReturnData
): Promise<{success: boolean; createdReturns?: string[]; message?: string; error?: string}> {
  const csrfToken = window.csrf_token;
  try {
    const response = await fetch(`/api/method/klik_pos.api.sales_invoice.create_multi_invoice_return`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
         'X-Frappe-CSRF-Token': csrfToken
      },
      body: new URLSearchParams({
        return_data: JSON.stringify(returnData)
      }).toString(),
       credentials: 'include'
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || 'Failed to create multi-invoice return');
    }

    // Handle both response formats
    const result = data.message || data;

    if (!result.success) {
      throw new Error(result.message || 'Failed to create multi-invoice return');
    }

    return {
      success: true,
      createdReturns: result.created_returns,
      message: result.message
    };

          //eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    console.error('Error creating multi-invoice return:', error);
    return {
      success: false,
      error: error.message || 'Failed to create multi-invoice return'
    };
  }
}

export async function getValidSalesInvoices(
  customer: string,
  itemCode: string,
  startDate: string,
  shippingAddress?: string,
  searchText?: string
) {
  try {
    const filters = {
      customer,
      item_code: itemCode,
      start_date: startDate,
      ...(shippingAddress && { shipping_address: shippingAddress })
    };

    const params = new URLSearchParams({
      doctype: 'Sales Invoice',
      txt: searchText || '',
      searchfield: 'name',
      start: '0',
      page_len: '20',
      filters: JSON.stringify(filters)
    });

    const response = await fetch(`/api/method/klik_pos.api.sales_invoice.get_valid_sales_invoices?${params}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || 'Failed to fetch valid sales invoices');
    }

    return {
      success: true,
      data: data.message
    };

          //eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    console.error('Error fetching valid sales invoices:', error);
    return {
      success: false,
      error: error.message || 'Failed to fetch valid sales invoices'
    };
  }
}
