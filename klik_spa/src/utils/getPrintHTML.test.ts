import { afterEach, describe, expect, it, vi } from "vitest";
import { getPrintFormatHTML } from "./getPrintHTML";

afterEach(() => vi.unstubAllGlobals());

describe("getPrintFormatHTML", () => {
  it("asks for the page without its letterhead - a preview need not wait for it", async () => {
    const fetch = vi.fn().mockResolvedValue({ json: async () => ({ message: { html: "<p/>", style: "" } }) });
    vi.stubGlobal("fetch", fetch);

    await getPrintFormatHTML({ doctype: "Sales Invoice", name: "POS-01624" }, "SI");

    const url = new URL(fetch.mock.calls[0]![0], "http://site");
    expect(url.searchParams.get("no_letterhead")).toBe("1");
    expect(url.searchParams.get("name")).toBe("POS-01624");
    expect(url.searchParams.get("print_format")).toBe("SI");
  });
});
