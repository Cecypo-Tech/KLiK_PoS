import { afterEach, describe, expect, it, vi } from "vitest";

import { PRINT_IMAGE_METHOD, copyPrintImage, fetchPrintImage } from "./copyAsImage";

function pngResponse() {
  return new Response(new Uint8Array([137, 80, 78, 71]), { status: 200, headers: { "Content-Type": "image/png" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("fetchPrintImage", () => {
  it("asks PowerPack for the order's print as a PNG", async () => {
    const fetchImpl = vi.fn(async () => pngResponse());
    const blob = await fetchPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl, csrfToken: "tok" });

    expect(fetchImpl).toHaveBeenCalledWith(`${PRINT_IMAGE_METHOD}?doctype=Sales+Order&name=SAL-ORD-1`, {
      credentials: "same-origin",
      headers: { "X-Frappe-CSRF-Token": "tok" },
    });
    expect(blob.type).toBe("image/png");
  });

  it("surfaces the server's own message on a refusal", async () => {
    const body = { _server_messages: JSON.stringify([JSON.stringify({ message: "Copy as Image is turned off in PowerPack Settings" })]) };
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(body), { status: 417 }));
    await expect(fetchPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl })).rejects.toThrow(
      "Copy as Image is turned off in PowerPack Settings"
    );
  });
});

describe("copyPrintImage", () => {
  it("puts the image on the clipboard", async () => {
    const write = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { clipboard: { write } });
    vi.stubGlobal("ClipboardItem", class { constructor(public items: unknown) {} });
    const notify = vi.fn();

    await copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl: vi.fn(async () => pngResponse()), notify });

    expect(write).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenLastCalledWith("Image copied", "success");
  });

  it("explains a failed render instead of downloading nothing", async () => {
    vi.stubGlobal("navigator", { clipboard: { write: vi.fn(async () => Promise.reject(new Error("refused"))) } });
    vi.stubGlobal("ClipboardItem", class { constructor(public items: unknown) {} });
    const notify = vi.fn();
    const fetchImpl = vi.fn(async () => new Response("{}", { status: 500 }));

    await copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl, notify });

    expect(notify).toHaveBeenLastCalledWith("Failed to create the image", "error");
  });
});
