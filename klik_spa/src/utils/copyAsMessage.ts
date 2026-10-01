/**
 * Runs the site's "Copy as Message" Client Script (cecypo_powerpack, Sales Order) for a held
 * order, as the desk form's Powerup > Copy as Message would.
 *
 * The script lives in the site, not in an app: the site edits it (its bank details sit in
 * the script). So the till does not keep a copy of the message; the server hands over the
 * script's source (klik_pos.api.sales_order.get_held_order_share_tools) and it runs here
 * against the few desk globals it uses. It registers a form handler; that handler's
 * refresh adds the button, and the button's click is what builds and copies the message.
 */

export interface DeskShimDeps {
  /** frappe.call: POST /api/method/<method>, resolving to the response's `message`. */
  call: (method: string, args: Record<string, unknown>) => Promise<unknown>;
  /** frappe.show_alert and frappe.msgprint. */
  alert: (message: string, ok: boolean) => void;
  formatCurrency: (value: number, currency?: string) => string;
  formatDate: (date: string) => string;
}

export const COPY_AS_MESSAGE_LABEL = "Copy as Message";

type Handler = (frm: unknown) => unknown;
type FormHandlers = Record<string, Handler | undefined>;
type ClickHandler = () => unknown;

interface CallOptions {
  method: string;
  args?: Record<string, unknown>;
  callback?: (r: { message: unknown }) => void;
  error?: (e: unknown) => void;
}

/** frappe's __(): the text with {0}, {1}... filled in. */
export function translate(text: string, args?: unknown[]): string {
  if (!args) return text;
  return text.replace(/\{(\d+)\}/g, (placeholder, index) =>
    args[Number(index)] === undefined ? placeholder : String(args[Number(index)])
  );
}

export function flt(value: unknown): number {
  const n = parseFloat(String(value ?? ""));
  return Number.isFinite(n) ? n : 0;
}

function cint(value: unknown): number {
  return Math.trunc(flt(value));
}

function plainText(message: unknown): string {
  return String(message ?? "").replace(/<[^>]*>/g, "");
}

export async function runCopyAsMessage(
  script: string,
  doc: Record<string, unknown> & { doctype: string },
  deps: DeskShimDeps
): Promise<void> {
  const handlers: Record<string, FormHandlers[]> = {};
  const frappeShim = {
    ui: {
      form: {
        on: (doctype: string, formHandlers: FormHandlers) => {
          (handlers[doctype] ??= []).push(formHandlers);
        },
      },
    },
    call: ({ method, args, callback, error }: CallOptions) =>
      deps.call(method, args ?? {}).then(
        (message) => callback?.({ message }),
        (e) => (error ? error(e) : deps.alert(plainText((e as Error)?.message ?? e), false))
      ),
    show_alert: (options: string | { message?: string; indicator?: string }) =>
      typeof options === "string"
        ? deps.alert(plainText(options), true)
        : deps.alert(plainText(options.message), options.indicator !== "red"),
    msgprint: (message: unknown) =>
      deps.alert(plainText(typeof message === "object" && message ? (message as { message?: string }).message : message), false),
    datetime: { str_to_user: (date: string) => (date ? deps.formatDate(date) : "") },
  };

  // The script is the site's own desk code, which every desk user's browser already runs.
  new Function("frappe", "__", "flt", "cint", "format_currency", script)(
    frappeShim,
    translate,
    flt,
    cint,
    deps.formatCurrency
  );

  let click: ClickHandler | undefined;
  const frm = {
    doc,
    doctype: doc.doctype,
    is_new: () => false,
    is_dirty: () => false,
    add_custom_button: (label: string, action: ClickHandler) => {
      if (label === COPY_AS_MESSAGE_LABEL) click = action;
    },
  };
  for (const formHandlers of handlers[doc.doctype] ?? []) {
    await formHandlers.refresh?.(frm);
  }
  if (!click) throw new Error("The site's Copy as Message script offered nothing for this order.");
  await click();
}
