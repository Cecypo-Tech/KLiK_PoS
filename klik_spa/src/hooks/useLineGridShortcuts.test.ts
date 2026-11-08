import { describe, expect, it, vi } from "vitest";
import { OVERLAY_SELECTOR, overlayOpen } from "./useLineGridShortcuts";

vi.mock("react-toastify", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));

const root = (match: boolean) => ({ querySelector: (sel: string) => (match && sel === OVERLAY_SELECTOR ? {} : null) });

describe("overlayOpen (grid keys stand down under a dialog)", () => {
  it("is true when a dialog or full-screen overlay is mounted", () => {
    expect(overlayOpen(root(true))).toBe(true);
  });

  it("is false otherwise", () => {
    expect(overlayOpen(root(false))).toBe(false);
  });

  it("covers role=dialog, aria-modal and the fixed inset-0 overlays (salesperson, camera scanner)", () => {
    for (const s of ['[role="dialog"]', '[aria-modal="true"]', ".fixed.inset-0"]) expect(OVERLAY_SELECTOR).toContain(s);
  });
});
