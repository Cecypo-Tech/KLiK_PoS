import { describe, expect, it } from "vitest";
import { staleDraftNotice } from "./staleDraft";

describe("staleDraftNotice", () => {
  it("lets a cancelled draft be rung up again as a new sale", () => {
    const notice = staleDraftNotice("POS-01190", 2);
    expect(notice.message).toContain("POS-01190");
    expect(notice.message).toMatch(/cancelled/);
    expect(notice.message).toMatch(/new invoice/);
    expect(notice.level).toBe("warning");
  });

  it("warns before a sale that was already submitted is rung up twice", () => {
    const notice = staleDraftNotice("POS-01190", 1);
    expect(notice.message).toMatch(/already submitted/);
    expect(notice.message).toMatch(/charged twice/);
    expect(notice.level).toBe("error");
  });
});
