import JsBarcode from "jsbarcode";

type BarcodeOptions = Record<string, unknown> & { format?: string };
type Draw = (element: Element, value: string, options: BarcodeOptions) => void;

/** JsBarcode options for a Barcode field, as Frappe's desk print preview builds them.
 *
 * Options that are not JSON are ignored, as the desk preview does; /printview would leave
 * such a barcode blank.
 */
export function barcodeOptions(value: string, fieldOptions: string | undefined): BarcodeOptions {
  const options: BarcodeOptions = { fontSize: "16", width: "3", height: "50" };
  try {
    const parsed = fieldOptions ? JSON.parse(fieldOptions) : null;
    if (parsed && typeof parsed === "object") Object.assign(options, parsed);
  } catch {
    // A field's options that are not JSON are not barcode options.
  }
  if (options.format === "EAN") options.format = value.length === 8 ? "EAN8" : "EAN13";
  return options;
}

/** Draw the barcodes Frappe leaves for its print page's script to draw.
 *
 * A Barcode field prints as an empty `<svg data-barcode-value>`; /printview and the desk
 * preview fill it with JsBarcode. The preview frame runs no scripts, so this page draws
 * them into the frame's page. A value that cannot be drawn is left empty, as Frappe does.
 */
export function drawPreviewBarcodes(page: Document | null | undefined, draw: Draw = JsBarcode as unknown as Draw): void {
  if (!page) return;
  for (const svg of Array.from(page.querySelectorAll<SVGSVGElement>("svg[data-barcode-value]"))) {
    const value = svg.dataset.barcodeValue;
    if (!value) continue;
    try {
      draw(svg, value, { ...barcodeOptions(value, svg.dataset.options), xmlDocument: svg.ownerDocument });
      svg.setAttribute("width", "100%");
    } catch (error) {
      console.warn("Print preview: could not draw barcode", value, error);
    }
  }
}
