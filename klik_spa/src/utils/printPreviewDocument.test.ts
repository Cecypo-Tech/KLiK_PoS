import { describe, expect, it } from "vitest";
import { buildPrintPreviewDocument, parsedPreviewPage, previewFrameHeight, unpinFixedElements } from "./printPreviewDocument";

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

  it("keeps a Print Style's @import first in its style element, where CSS honours it", () => {
    const doc = buildPrintPreviewDocument("", "@import url('https://fonts.googleapis.com/css?family=Lato');\n.x{}");
    expect(doc).toMatch(/<style>@import url\('https:\/\/fonts\.googleapis\.com/);
  });

  it("never scrolls the frame up and down - the frame is as tall as the page", () => {
    expect(buildPrintPreviewDocument("", "")).toMatch(/html\s*{\s*overflow-y:\s*hidden;\s*}/);
  });

  it("opens links outside the preview", () => {
    expect(buildPrintPreviewDocument("", "")).toContain('<base target="_blank">');
  });

  it("does not let the style close its own tag early", () => {
    const doc = buildPrintPreviewDocument("<p>body</p>", "a{} </style><script>alert(1)</script>");
    expect(doc).not.toContain("</style><script>");
    expect(doc.match(/<\/style>/gi)).toHaveLength(doc.match(/<style>/gi)!.length);
  });

  it("tolerates a missing style or html", () => {
    const doc = buildPrintPreviewDocument(undefined, undefined);
    expect(doc).toContain("<body data-print-preview>");
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

describe("previewFrameHeight", () => {
  const frame = ({ rect, scrollHeight, innerHeight = 500, clientHeight = 500 }: Record<string, number>) =>
    ({
      body: { getBoundingClientRect: () => ({ height: rect }), scrollHeight },
      documentElement: { clientHeight },
      defaultView: { innerHeight },
    }) as unknown as Document;

  it("is the page's height", () => {
    expect(previewFrameHeight(frame({ rect: 631.2, scrollHeight: 631 }))).toBe(632);
  });

  it("counts the content of a format that sets its body to the frame's height", () => {
    // html, body { height: 100% } in a frame that starts 0px tall: the body is 0px.
    expect(previewFrameHeight(frame({ rect: 0, scrollHeight: 732 }))).toBe(732);
  });

  it("leaves room for a sideways scrollbar, so it does not hide the foot of the page", () => {
    expect(previewFrameHeight(frame({ rect: 717, scrollHeight: 717, innerHeight: 732, clientHeight: 717 }))).toBe(732);
  });

  it("is 0 for a page that has not loaded", () => {
    expect(previewFrameHeight(null)).toBe(0);
  });
});

describe("parsedPreviewPage", () => {
  const page = (readyState: string, marked = true) =>
    ({ readyState, body: { hasAttribute: (name: string) => marked && name === "data-print-preview" } }) as unknown as Document;
  const frame = (contentDocument: Document | null) => ({ contentDocument }) as HTMLIFrameElement;

  it("is the preview page once its markup is read, before its images load", () => {
    const parsed = page("interactive");
    expect(parsedPreviewPage(frame(parsed), null)).toBe(parsed);
    expect(parsedPreviewPage(frame(page("complete")), null)).not.toBeNull();
  });

  it("is not a page still being read - its footer may not be there yet", () => {
    expect(parsedPreviewPage(frame(page("loading")), null)).toBeNull();
  });

  it("is not the blank page a frame starts on", () => {
    expect(parsedPreviewPage(frame(page("complete", false)), null)).toBeNull();
  });

  it("is not the previous invoice's page while the next one is on its way", () => {
    const previous = page("complete");
    expect(parsedPreviewPage(frame(previous), previous)).toBeNull();
  });

  it("is nothing for a frame with no page", () => {
    expect(parsedPreviewPage(null, null)).toBeNull();
    expect(parsedPreviewPage(frame(null), null)).toBeNull();
  });
});
