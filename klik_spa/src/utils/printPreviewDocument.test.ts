import { describe, expect, it } from "vitest";
import { buildPrintPreviewDocument, unpinFixedElements } from "./printPreviewDocument";

describe("buildPrintPreviewDocument", () => {
  it("is a whole document holding the format's style and html", () => {
    const doc = buildPrintPreviewDocument('<div class="print-format"><b>POS-01624</b></div>', ".po-footer { position: fixed; }");
    expect(doc.startsWith("<!doctype html>")).toBe(true);
    expect(doc).toContain('<meta charset="utf-8">');
    expect(doc).toContain(".po-footer { position: fixed; }");
    expect(doc).toContain('<div class="print-format"><b>POS-01624</b></div>');
  });

  it("prints on white paper whatever the app's theme", () => {
    const doc = buildPrintPreviewDocument("", "");
    expect(doc).toMatch(/background:\s*#fff/);
    expect(doc).toMatch(/color:\s*#000/);
  });

  it("keeps the format's margins inside the body the frame is sized to", () => {
    expect(buildPrintPreviewDocument("", "")).toMatch(/body\s*{\s*display:\s*flow-root;\s*}/);
  });

  it("opens links outside the preview", () => {
    expect(buildPrintPreviewDocument("", "")).toContain('<base target="_blank">');
  });

  it("does not let the style close its own tag early", () => {
    const doc = buildPrintPreviewDocument("<p>body</p>", "a{} </style><script>alert(1)</script>");
    expect(doc).not.toContain("</style><script>");
    expect(doc.match(/<\/style>/gi)).toHaveLength(1);
  });

  it("tolerates a missing style or html", () => {
    const doc = buildPrintPreviewDocument(undefined, undefined);
    expect(doc).toContain("<body>");
    expect(doc).not.toContain("undefined");
  });
});

describe("unpinFixedElements", () => {
  const element = (position: string) => {
    const set: Array<[string, string, string]> = [];
    return { position, set, style: { setProperty: (...args: [string, string, string]) => set.push(args) } };
  };
  const page = (elements: ReturnType<typeof element>[]) =>
    ({
      body: { querySelectorAll: () => elements },
      defaultView: { getComputedStyle: (el: { position: string }) => ({ position: el.position }) },
    }) as unknown as Document;

  it("puts a fixed footer back in the flow, where the format wrote it", () => {
    const footer = element("fixed");
    const table = element("static");
    const watermark = element("absolute");

    unpinFixedElements(page([table, footer, watermark]));

    expect(footer.set).toEqual([["position", "static", "important"]]);
    expect(table.set).toEqual([]);
    expect(watermark.set).toEqual([]);
  });

  it("does nothing to a page that has not loaded", () => {
    expect(() => unpinFixedElements(null)).not.toThrow();
    expect(() => unpinFixedElements({ body: null, defaultView: null } as unknown as Document)).not.toThrow();
  });
});
