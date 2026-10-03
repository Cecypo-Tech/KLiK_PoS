import { describe, expect, it, vi } from "vitest";
import { barcodeOptions, drawPreviewBarcodes } from "./previewBarcodes";

describe("barcodeOptions", () => {
  it("are Frappe's print defaults", () => {
    expect(barcodeOptions("12345", undefined)).toEqual({ fontSize: "16", width: "3", height: "50" });
  });

  it("take the Barcode field's own options over the defaults", () => {
    expect(barcodeOptions("12345", '{"format": "CODE39", "height": "30"}')).toEqual({
      fontSize: "16",
      width: "3",
      height: "30",
      format: "CODE39",
    });
  });

  it("read EAN as EAN-8 or EAN-13 by the value's length, as Frappe does", () => {
    expect(barcodeOptions("96385074", '{"format": "EAN"}').format).toBe("EAN8");
    expect(barcodeOptions("5901234123457", '{"format": "EAN"}').format).toBe("EAN13");
  });

  it("ignore options that are not JSON", () => {
    expect(barcodeOptions("12345", "not json")).toEqual({ fontSize: "16", width: "3", height: "50" });
  });
});

describe("drawPreviewBarcodes", () => {
  const svg = (value: string, options?: string) => {
    const attributes: Record<string, string> = {};
    return {
      dataset: { barcodeValue: value, options },
      ownerDocument: { name: "frame page" },
      attributes,
      setAttribute: (name: string, v: string) => (attributes[name] = v),
    };
  };
  const page = (svgs: ReturnType<typeof svg>[]) =>
    ({ querySelectorAll: (selector: string) => (selector === "svg[data-barcode-value]" ? svgs : []) }) as unknown as Document;

  it("draws each placeholder Frappe left for its print page's script, in the frame's own page", () => {
    const first = svg("ITEM-001");
    const second = svg("5901234123457", '{"format": "EAN"}');
    const draw = vi.fn();

    drawPreviewBarcodes(page([first, second]), draw);

    expect(draw).toHaveBeenCalledWith(first, "ITEM-001", {
      fontSize: "16", width: "3", height: "50", xmlDocument: first.ownerDocument,
    });
    expect(draw.mock.calls[1]![2].format).toBe("EAN13");
    expect(first.attributes.width).toBe("100%");
    expect(second.attributes.width).toBe("100%");
  });

  it("draws the rest when one value cannot be a barcode", () => {
    const bad = svg("not-a-number", '{"format": "EAN"}');
    const good = svg("ITEM-001");
    const draw = vi.fn((element) => {
      if (element === bad) throw new Error("invalid EAN");
    });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(() => drawPreviewBarcodes(page([bad, good]), draw)).not.toThrow();

    expect(good.attributes.width).toBe("100%");
    expect(bad.attributes.width).toBeUndefined();
    warn.mockRestore();
  });

  it("skips an empty value and a page that has not loaded", () => {
    const draw = vi.fn();
    drawPreviewBarcodes(page([svg("")]), draw);
    drawPreviewBarcodes(null, draw);
    expect(draw).not.toHaveBeenCalled();
  });
});
