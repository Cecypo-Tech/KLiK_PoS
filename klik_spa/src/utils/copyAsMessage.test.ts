import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { deferredClipboardText, formatSystemDate, plainText, runCopyAsMessage, translate, type DeskShimDeps } from "./copyAsMessage";

// PowerPack's shipped script, when the bench has the app beside this one.
const POWERPACK_SCRIPT = fileURLToPath(
  new URL("../../../../cecypo_powerpack/cecypo_powerpack/client_scripts/copy_as_message_sales_order.js", import.meta.url)
);
const LINK = "https://dev.cecypo.tech/s/SAL-ORD-2026-00042-x7kQ";

const order = {
  doctype: "Sales Order",
  name: "SAL-ORD-2026-00042",
  docstatus: 0,
  customer: "CUST-1",
  customer_name: "Mimosa Ltd",
  company: "Dev Co",
  currency: "KES",
  transaction_date: "2026-10-02",
  delivery_date: "2026-10-05",
  grand_total: 1500,
  rounded_total: 1500,
  advance_paid: 0,
  per_billed: 0,
  status: "Draft",
};

function deps(overrides: Partial<DeskShimDeps> = {}) {
  return {
    call: vi.fn(async () => LINK),
    alert: vi.fn(),
    formatCurrency: (value: number) => `Sh ${value.toFixed(2)}`,
    formatDate: (date: string) => date.split("-").reverse().join("-"),
    writeText: vi.fn(async () => undefined),
    ...overrides,
  };
}

const button = (body: string) =>
  `frappe.ui.form.on('Sales Order', { refresh(frm) { frm.add_custom_button(__('Copy as Message'), async () => { ${body} }, __('Powerup')); } });`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("translate and plainText", () => {
  it("fills placeholders like frappe's __", () => {
    expect(translate("Sales Order {0} dated {1}", ["SO-1", "02-10-2026"])).toBe("Sales Order SO-1 dated 02-10-2026");
    expect(translate("Total: {0}")).toBe("Total: {0}");
  });

  it("turns a desk message into text", () => {
    expect(plainText("<b>Tom &amp; Co</b><br>owes")).toBe("Tom & Co\nowes");
  });
});

describe("runCopyAsMessage", () => {
  it("runs the script's own button and copies what it builds", async () => {
    const d = deps();
    await runCopyAsMessage(
      button(`
        const url = await new Promise((resolve) => frappe.call({
          method: 'cecypo_powerpack.api.get_document_public_link',
          args: { doctype: frm.doc.doctype, name: frm.doc.name },
          callback: (r) => resolve(r.message),
        }));
        await navigator.clipboard.writeText(__('{0}: {1}', [frm.doc.name, url]));
        frappe.show_alert({ message: __('Message copied'), indicator: 'green' });`),
      order,
      d
    );

    expect(d.call).toHaveBeenCalledWith("cecypo_powerpack.api.get_document_public_link", {
      doctype: "Sales Order",
      name: "SAL-ORD-2026-00042",
    });
    expect(d.writeText).toHaveBeenCalledWith(`SAL-ORD-2026-00042: ${LINK}`);
    expect(d.alert).toHaveBeenCalledWith("Message copied", true);
  });

  it("supports awaiting frappe.call, its string form, and xcall", async () => {
    const d = deps();
    await runCopyAsMessage(
      button(`
        const r = await frappe.call('m.one', { a: 1 });
        const x = await frappe.xcall('m.two');
        await navigator.clipboard.writeText(r.message + ' ' + x);`),
      order,
      d
    );
    expect(d.call).toHaveBeenNthCalledWith(1, "m.one", { a: 1 });
    expect(d.writeText).toHaveBeenCalledWith(`${LINK} ${LINK}`);
  });

  it("waits for a callback-style script and reports what throws inside its callback", async () => {
    const d = deps();
    const run = runCopyAsMessage(
      button(`frappe.call({ method: 'm', callback: (r) => { r.message.nope.boom; } });`),
      order,
      d
    );
    await expect(run).rejects.toThrow(/script failed here/);
  });

  it("tolerates jQuery-style chaining on the button", async () => {
    const d = deps();
    const script = `frappe.ui.form.on('Sales Order', { refresh(frm) {
      frm.add_custom_button(__('Copy as Message'), () => navigator.clipboard.writeText('ok')).addClass('btn-primary').css({});
    } });`;
    await runCopyAsMessage(script, order, d);
    expect(d.writeText).toHaveBeenCalledWith("ok");
  });

  it("names the script when it breaks on something the till lacks", async () => {
    await expect(runCopyAsMessage(button("frappe.ui.toolbar.clear_cache();"), order, deps())).rejects.toThrow(
      /Copy as Message script failed here/
    );
  });

  it("shows the server's message for a failed call the script does not catch, as desk does", async () => {
    const d = deps({ call: vi.fn(async () => Promise.reject(new Error("Not permitted"))) });
    await expect(runCopyAsMessage(button("await frappe.call('m');"), order, d)).rejects.toThrow(/Not permitted/);
    expect(d.alert).toHaveBeenCalledWith("Not permitted", false);
  });

  it("reports a failed call through the script's own error callback", async () => {
    const d = deps({ call: vi.fn(async () => Promise.reject(new Error("boom"))) });
    await runCopyAsMessage(
      button(`
        try {
          await new Promise((resolve, reject) => frappe.call({ method: 'x', args: {}, callback: resolve, error: reject }));
        } catch (e) { frappe.msgprint(__('Failed to generate the public link')); }`),
      order,
      d
    );
    expect(d.alert).toHaveBeenCalledWith("Failed to generate the public link", false);
  });

  it("says so when the script adds no Copy as Message button", async () => {
    await expect(
      runCopyAsMessage("frappe.ui.form.on('Sales Order', { refresh() {} });", order, deps())
    ).rejects.toThrow(/offered nothing/);
  });

  it("ignores handlers registered for other doctypes", async () => {
    const script = "frappe.ui.form.on('Quotation', { refresh(frm) { frm.add_custom_button('Copy as Message', () => {}); } });";
    await expect(runCopyAsMessage(script, order, deps())).rejects.toThrow(/offered nothing/);
  });

  it.skipIf(!existsSync(POWERPACK_SCRIPT))("runs PowerPack's shipped Sales Order script unchanged", async () => {
    const d = deps();

    await runCopyAsMessage(readFileSync(POWERPACK_SCRIPT, "utf8"), order, d);

    expect(d.writeText).toHaveBeenCalledWith(
      [
        "Mimosa Ltd,",
        "Sales Order SAL-ORD-2026-00042 dated 02-10-2026",
        "Delivery Date: 05-10-2026",
        "Total: Sh 1500.00",
        "Status: Draft",
        `View it here: ${LINK}`,
      ].join("\n")
    );
    expect(d.alert).toHaveBeenCalledWith("Message copied", true);
  });
});

describe("deferredClipboardText", () => {
  it("hands the clipboard a pending item at once and fills it when the script writes", async () => {
    const items: Array<Record<string, Promise<Blob>>> = [];
    vi.stubGlobal("ClipboardItem", class {
      constructor(public data: Record<string, Promise<Blob>>) {
        items.push(data);
      }
    });
    const write = vi.fn(async (list: Array<{ data: Record<string, Promise<Blob>> }>) => {
      await list[0]?.data["text/plain"];
    });
    const clipboard = { write, writeText: vi.fn() } as unknown as Clipboard;

    const writer = deferredClipboardText(clipboard);
    expect(write).toHaveBeenCalledTimes(1); // during the click, before any text exists

    await writer.writeText("hello");
    expect(await (await items[0]?.["text/plain"])?.text()).toBe("hello");
  });

  it("falls back to writeText where ClipboardItem is missing", async () => {
    vi.stubGlobal("ClipboardItem", undefined);
    const clipboard = { writeText: vi.fn(async () => undefined) } as unknown as Clipboard;
    await deferredClipboardText(clipboard).writeText("hi");
    expect(clipboard.writeText).toHaveBeenCalledWith("hi");
  });
});

describe("formatSystemDate", () => {
  it("follows the site's date format", () => {
    expect(formatSystemDate("2026-10-02", "dd-mm-yyyy")).toBe("02-10-2026");
    expect(formatSystemDate("2026-10-02", "mm/dd/yyyy")).toBe("10/02/2026");
    expect(formatSystemDate("2026-10-02 09:00:00", "yyyy-mm-dd")).toBe("2026-10-02");
    expect(formatSystemDate("", "dd-mm-yyyy")).toBe("");
  });
});
