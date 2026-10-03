type Invoice = {
  doctype: string;
  name: string;
  [key: string]: unknown; // to allow other properties
};

type PrintHTMLResponse = {
  html: string;
  style: string;
};

/** The print format's html and style for klik's preview.
 *
 * Without the letterhead: it is the slow part of the page (an image, often large), and the
 * preview shows the invoice, not the company's stationery. Printing asks for its own page.
 */
export async function getPrintFormatHTML(
  invoice: Invoice,
  printFormat: string
): Promise<PrintHTMLResponse> {
  const res = await fetch(
    `/api/method/frappe.www.printview.get_html_and_style?doc=${invoice.doctype}&name=${invoice.name}&print_format=${printFormat}&no_letterhead=1`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    }
  );

  const data = await res.json();
  return data.message as PrintHTMLResponse;
}
