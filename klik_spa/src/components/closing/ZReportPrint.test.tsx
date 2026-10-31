import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ZReportPrint, { canPrintZReport } from "./ZReportPrint";

vi.mock("react-toastify", () => ({ toast: {} }));

describe("ZReportPrint", () => {
  it("renders Print Z-report for the closing entry", () => {
    const html = renderToStaticMarkup(<ZReportPrint name="POS-CLO-1" onContinue={() => {}} />);
    expect(html).toContain("Print Z-report");
    expect(html).toContain("POS-CLO-1");
  });

  it("is offered only when QZ is on and the user may close", () => {
    expect(canPrintZReport({ custom_enable_qz_print: 1 }, { can_close_shift: true })).toBe(true);
    expect(canPrintZReport({ custom_enable_qz_print: 1 }, {})).toBe(true);
    expect(canPrintZReport({ custom_enable_qz_print: 1 }, { can_close_shift: false })).toBe(false);
    expect(canPrintZReport({ custom_enable_qz_print: 0 }, { can_close_shift: true })).toBe(false);
    expect(canPrintZReport(null, null)).toBe(false);
  });
});
