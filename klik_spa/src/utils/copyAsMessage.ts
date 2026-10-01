/**
 * Runs the site's "Copy as Message" Client Script (cecypo_powerpack, Sales Order) for a held
 * order, as the desk form's Powerup > Copy as Message would.
 *
 * The script lives in the site, not in an app: the site edits it (its bank details sit in
 * the script). So the till does not keep a copy of the message; the server hands over the
 * script's source (klik_pos.api.sales_order.get_held_order_share_tools) and it runs here
 * against the desk globals such scripts use. It registers a form handler; that handler's
 * refresh adds the button, and the button's click builds and copies the message.
 */

export interface DeskShimDeps {
  /** POST /api/method/<method>, resolving to the response's `message`. */
  call: (method: string, args: Record<string, unknown>) => Promise<unknown>;
  /** frappe.show_alert and frappe.msgprint. */
  alert: (message: string, ok: boolean) => void;
  formatCurrency: (value: number, currency?: string) => string;
  formatDate: (date: string) => string;
  /** What the script's navigator.clipboard.writeText writes to. */
  writeText: (text: string) => Promise<void>;
  user?: string;
}

export const COPY_AS_MESSAGE_LABEL = "Copy as Message";

type FormHandlers = Record<string, ((frm: unknown) => unknown) | undefined>;
type ClickHandler = () => unknown;

interface CallOptions {
  method: string;
  args?: Record<string, unknown>;
  callback?: (r: { message: unknown }) => void;
  error?: (e: unknown) => void;
  always?: (r: unknown) => void;
}

/** frappe's __(): the text with {0}, {1}... filled in. */
export function translate(text: string, args?: unknown[]): string {
  if (!args) return String(text);
  return String(text).replace(/\{(\d+)\}/g, (placeholder, index) =>
    args[Number(index)] === undefined ? placeholder : String(args[Number(index)])
  );
}

export function flt(value: unknown, precision?: number): number {
  const n = parseFloat(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(n)) return 0;
  return precision === undefined ? n : Number(n.toFixed(precision));
}

function cint(value: unknown): number {
  return Math.trunc(flt(value));
}

const ENTITIES: Record<string, string> = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };

export function plainText(message: unknown): string {
  return String(message ?? "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (entity) => ENTITIES[entity] ?? entity);
}

/** Stands in for the jQuery objects desk calls return: every method returns it again. */
function chainable(): unknown {
  const target = () => proxy;
  const proxy: unknown = new Proxy(target, { get: (_t, key) => (key === "then" ? undefined : target) });
  return proxy;
}

export class CopyScriptError extends Error {}

export async function runCopyAsMessage(
  script: string,
  doc: Record<string, unknown> & { doctype: string },
  deps: DeskShimDeps
): Promise<void> {
  const handlers: Record<string, FormHandlers[]> = {};
  // Work a callback-style script starts and does not return to us: waited on before the run
  // counts as done. An exception inside one of its callbacks fails the run here instead of
  // vanishing as an unhandled rejection.
  const pending = new Set<Promise<unknown>>();
  const failures: unknown[] = [];
  const guarded = <A extends unknown[]>(fn: ((...args: A) => unknown) | undefined, ...args: A) => {
    try {
      fn?.(...args);
    } catch (e) {
      failures.push(e);
    }
  };

  const call = (methodOrOptions: string | CallOptions, maybeArgs?: Record<string, unknown>) => {
    const options: CallOptions =
      typeof methodOrOptions === "string" ? { method: methodOrOptions, args: maybeArgs } : methodOrOptions;
    const request = deps.call(options.method, options.args ?? {}).then(
      (message) => {
        const r = { message };
        guarded(options.callback, r);
        guarded(options.always, r);
        return r;
      },
      (e) => {
        if (options.error) {
          guarded(options.error, e);
          guarded(options.always, e);
          return { message: undefined };
        }
        // As desk's frappe.call does: the server's message is shown, and the promise rejects.
        deps.alert(plainText((e as Error)?.message ?? e), false);
        throw e;
      }
    );
    const settled = request.then(
      () => undefined,
      () => undefined
    );
    pending.add(settled);
    void settled.finally(() => pending.delete(settled));
    return request;
  };

  const frappeShim = {
    ui: {
      form: {
        on: (doctype: string, formHandlers: FormHandlers) => {
          (handlers[doctype] ??= []).push(formHandlers);
        },
      },
    },
    call,
    xcall: (method: string, args?: Record<string, unknown>) => call(method, args).then((r) => r.message),
    show_alert: (options: string | { message?: string; indicator?: string }) =>
      typeof options === "string"
        ? deps.alert(plainText(options), true)
        : deps.alert(plainText(options.message), options.indicator !== "red"),
    msgprint: (message: unknown) =>
      deps.alert(plainText(typeof message === "object" && message ? (message as { message?: string }).message : message), false),
    throw: (message: unknown) => {
      throw new CopyScriptError(plainText(typeof message === "object" && message ? (message as { message?: string }).message : message));
    },
    provide: (namespace: string) =>
      namespace.split(".").reduce<Record<string, unknown>>((node, key) => {
        node[key] ??= {};
        return node[key] as Record<string, unknown>;
      }, globalThis as unknown as Record<string, unknown>),
    boot: {},
    session: { user: deps.user ?? "" },
    datetime: {
      str_to_user: (date: string) => (date ? deps.formatDate(String(date)) : ""),
      get_today: () => new Date().toISOString().slice(0, 10),
    },
    format: (value: unknown) => String(value ?? ""),
  };
  const navigatorShim = { clipboard: { writeText: (text: string) => deps.writeText(String(text)) } };

  let click: ClickHandler | undefined;
  const frm = {
    doc,
    doctype: doc.doctype,
    docname: doc.name,
    is_new: () => false,
    is_dirty: () => false,
    add_custom_button: (label: string, action: ClickHandler) => {
      if (plainText(label).trim() === COPY_AS_MESSAGE_LABEL) click = action;
      return chainable();
    },
    remove_custom_button: () => undefined,
    set_value: () => Promise.resolve(),
    refresh_field: () => undefined,
    toggle_display: () => undefined,
    set_df_property: () => undefined,
    call: (method: string, args?: Record<string, unknown>) => call(method, args),
    page: chainable(),
  };

  try {
    // The script is the site's own desk code, which every desk user's browser already runs.
    new Function("frappe", "__", "flt", "cint", "format_currency", "navigator", "cur_frm", "$", script)(
      frappeShim,
      translate,
      flt,
      cint,
      deps.formatCurrency,
      navigatorShim,
      frm,
      chainable()
    );
    for (const formHandlers of handlers[doc.doctype] ?? []) {
      await formHandlers.refresh?.(frm);
    }
    if (!click) throw new CopyScriptError("The site's Copy as Message script offered nothing for this order.");
    await click();
    while (pending.size) await Promise.all([...pending]);
  } catch (e) {
    if (e instanceof CopyScriptError) throw e;
    throw new CopyScriptError(`The site's Copy as Message script failed here: ${plainText((e as Error)?.message ?? e)}`);
  }
  if (failures.length) {
    throw new CopyScriptError(
      `The site's Copy as Message script failed here: ${plainText((failures[0] as Error)?.message ?? failures[0])}`
    );
  }
}

/**
 * The clipboard writer for one Copy click. Safari lets a page write to the clipboard only
 * during the click, and the message is ready only after the order and its public link are
 * fetched. So the clipboard is handed a pending item now, and the script's writeText settles
 * it later. Where ClipboardItem is missing, writeText is used directly.
 */
export function deferredClipboardText(clipboard: Clipboard = navigator.clipboard) {
  if (typeof ClipboardItem === "undefined" || !clipboard?.write) {
    return { writeText: (text: string) => clipboard.writeText(text), done: () => undefined };
  }
  let resolveText!: (text: string) => void;
  let rejectText!: (e: unknown) => void;
  const text = new Promise<string>((resolve, reject) => {
    resolveText = resolve;
    rejectText = reject;
  });
  const written = clipboard.write([
    new ClipboardItem({ "text/plain": text.then((t) => new Blob([t], { type: "text/plain" })) }),
  ]);
  // A script that fails before writing rejects `text`; that failure is reported by the run.
  written.catch(() => undefined);
  return {
    writeText: (value: string) => {
      resolveText(value);
      return written;
    },
    /** Call when the run ends: a script that never wrote leaves nothing on the clipboard. */
    done: () => rejectText(new Error("Nothing was copied")),
  };
}

/** frappe.datetime.str_to_user for a date: "2026-10-02" in the site's date format
 * (System Settings), e.g. dd-mm-yyyy -> 02-10-2026. */
export function formatSystemDate(date: string, format: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date || "");
  if (!match) return date || "";
  const [, yyyy = "", mm = "", dd = ""] = match;
  return (format || "dd-mm-yyyy").replace(/yyyy/i, yyyy).replace(/mm/i, mm).replace(/dd/i, dd);
}
