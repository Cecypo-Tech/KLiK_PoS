import { describe, expect, it } from "vitest";
import { staleDraftNotice } from "./staleDraft";

describe("staleDraftNotice", () => {
  it("lets a cancelled draft be rung up again as a new sale", () => {
    const notice = staleDraftNotice("POS-01190", 2);
    expect(notice.message).toContain("POS-01190");
    expect(notice.message).toMatch(/cancelled/);
    expect(notice.message).toMatch(/new invoice/);
    expect(notice.level).toBe("warning");
    expect(notice.blockSubmit).toBe(false);
  });

  it("asks for M-Pesa to be taken again when the cancelled draft carried it", () => {
    expect(staleDraftNotice("POS-01190", 2, { wasMpesaDraft: true }).message).toMatch(/M-Pesa/);
  });

  it("blocks Submit when the draft was already submitted, so the sale is not charged twice", () => {
    const notice = staleDraftNotice("POS-01190", 1);
    expect(notice.message).toMatch(/already submitted/);
    expect(notice.level).toBe("error");
    expect(notice.blockSubmit).toBe(true);
  });

  it("treats an unknown state as submitted, the safe side", () => {
    expect(staleDraftNotice("POS-01190", Number.NaN).blockSubmit).toBe(true);
  });
});
