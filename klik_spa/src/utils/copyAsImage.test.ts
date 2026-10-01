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

    expect(fetchImpl).toHaveBeenCalledWith(
      `${PRINT_IMAGE_METHOD}?doctype=Sales+Order&name=SAL-ORD-1`,
      expect.objectContaining({ credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": "tok" } })
    );
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

  it("downloads the image when the clipboard refuses it", async () => {
    vi.stubGlobal("navigator", { clipboard: { write: vi.fn(async () => Promise.reject(new Error("refused"))) } });
    vi.stubGlobal("ClipboardItem", class { constructor(public items: unknown) {} });
    const click = vi.fn();
    vi.stubGlobal("document", {
      createElement: () => ({ click, remove: vi.fn(), set href(_v: string) {}, set download(_v: string) {} }),
      body: { appendChild: vi.fn() },
    });
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: vi.fn() });
    const notify = vi.fn();

    await copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl: vi.fn(async () => pngResponse()), notify });

    expect(click).toHaveBeenCalled();
    expect(notify).toHaveBeenLastCalledWith("Could not copy the image, so it was downloaded instead", "warning");
  });

  it("says it is still working on a repeat click, and takes clicks again once done", async () => {
    let finish!: (r: Response) => void;
    vi.stubGlobal("navigator", { clipboard: { write: vi.fn(async (items: Array<{ items: Record<string, Promise<Blob>> }>) => { await items[0].items["image/png"]; }) } });
    vi.stubGlobal("ClipboardItem", class { constructor(public items: unknown) {} });
    const notify = vi.fn();
    const fetchImpl = vi.fn(() => new Promise<Response>((resolve) => (finish = resolve)));

    const first = copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl, notify });
    await copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl, notify });
    expect(notify).toHaveBeenLastCalledWith("Still preparing the image…", "info");
    expect(fetchImpl).toHaveBeenCalledTimes(1);

    finish(pngResponse());
    await first;
    await copyPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl: vi.fn(async () => pngResponse()), notify });
    expect(notify).toHaveBeenLastCalledWith("Image copied", "success");
  });

  it("gives up on a render that never answers", async () => {
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))))
    );
    await expect(fetchPrintImage("Sales Order", "SAL-ORD-1", { fetchImpl }, 10)).rejects.toThrow(/took too long/);
  });
});
