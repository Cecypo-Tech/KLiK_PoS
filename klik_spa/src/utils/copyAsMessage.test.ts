import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { runCopyAsMessage, translate, type DeskShimDeps } from "./copyAsMessage";

// PowerPack's shipped script, when the bench has the app beside this one.
const POWERPACK_SCRIPT = fileURLToPath(
  new URL("../../../../cecypo_powerpack/cecypo_powerpack/client_scripts/copy_as_message_sales_order.js", import.meta.url)
);

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
    call: vi.fn(async () => "https://dev.cecypo.tech/s/SAL-ORD-2026-00042-x7kQ"),
    alert: vi.fn(),
    formatCurrency: (value: number, currency?: string) => `${currency} ${value.toFixed(2)}`,
    formatDate: (date: string) => date.split("-").reverse().join("-"),
    ...overrides,
  };
}

function stubClipboard() {
  const writeText = vi.fn(async () => undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  return writeText;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("translate", () => {
  it("fills placeholders like frappe's __", () => {
    expect(translate("Sales Order {0} dated {1}", ["SO-1", "02-10-2026"])).toBe("Sales Order SO-1 dated 02-10-2026");
    expect(translate("Total: {0}")).toBe("Total: {0}");
  });
});

describe("runCopyAsMessage", () => {
  it("runs the script's own button and copies what it builds", async () => {
    const writeText = stubClipboard();
    const d = deps();
    const script = `
      frappe.ui.form.on('Sales Order', {
        refresh(frm) {
          frm.add_custom_button(__('Copy as Message'), async () => {
            const url = await new Promise((resolve) => frappe.call({
              method: 'cecypo_powerpack.api.get_document_public_link',
              args: { doctype: frm.doc.doctype, name: frm.doc.name },
              callback: (r) => resolve(r.message),
            }));
            await navigator.clipboard.writeText(__('{0}: {1}', [frm.doc.name, url]));
            frappe.show_alert({ message: __('Message copied'), indicator: 'green' });
          }, __('Powerup'));
        },
      });`;

    await runCopyAsMessage(script, order, d);

    expect(d.call).toHaveBeenCalledWith("cecypo_powerpack.api.get_document_public_link", {
      doctype: "Sales Order",
      name: "SAL-ORD-2026-00042",
    });
    expect(writeText).toHaveBeenCalledWith("SAL-ORD-2026-00042: https://dev.cecypo.tech/s/SAL-ORD-2026-00042-x7kQ");
    expect(d.alert).toHaveBeenCalledWith("Message copied", true);
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

  it("reports a failed server call through the script's own error path", async () => {
    stubClipboard();
    const d = deps({ call: vi.fn(async () => Promise.reject(new Error("boom"))) });
    const script = `
      frappe.ui.form.on('Sales Order', { refresh(frm) {
        frm.add_custom_button(__('Copy as Message'), async () => {
          try {
            await new Promise((resolve, reject) => frappe.call({ method: 'x', args: {}, callback: resolve, error: reject }));
          } catch (e) { frappe.msgprint(__('Failed to generate the public link')); }
        });
      } });`;
    await runCopyAsMessage(script, order, d);
    expect(d.alert).toHaveBeenCalledWith("Failed to generate the public link", false);
  });

  it.skipIf(!existsSync(POWERPACK_SCRIPT))("runs PowerPack's shipped Sales Order script unchanged", async () => {
    const writeText = stubClipboard();
    const d = deps();

    await runCopyAsMessage(readFileSync(POWERPACK_SCRIPT, "utf8"), order, d);

    expect(writeText).toHaveBeenCalledWith(
      [
        "Mimosa Ltd,",
        "Sales Order SAL-ORD-2026-00042 dated 02-10-2026",
        "Delivery Date: 05-10-2026",
        "Total: KES 1500.00",
        "Status: Draft",
        "View it here: https://dev.cecypo.tech/s/SAL-ORD-2026-00042-x7kQ",
      ].join("\n")
    );
    expect(d.alert).toHaveBeenCalledWith("Message copied", true);
  });
});
