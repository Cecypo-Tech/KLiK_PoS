import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import PaymentHeader from "./PaymentHeader";

vi.mock("../../utils/printHandler", () => ({ handlePrintInvoice: vi.fn() }));

const orderComplete = (extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(
    <PaymentHeader
      invoiceSubmitted
      isAutoPrinting={false}
      invoiceData={{ name: "POS-01696" }}
      sharingMode={null}
      setSharingMode={() => {}}
      isProcessingPayment={false}
      isHoldingOrder={false}
      onClose={() => {}}
      handleViewInvoice={() => {}}
      finalizeCompletedOrderState={() => {}}
      posDetails={{}}
      onCopyOrder={() => {}}
      {...extra}
    />,
  );

describe("PaymentHeader on Order Complete (desktop)", () => {
  it("shows the QZ button with the print count as QZ-n", () => {
    const html = orderComplete({ onQzReprint: () => {}, qzCount: 3 });
    expect(html).toContain('title="QZ Print"');
    expect(html).toContain(">-3<");
  });

  it("shows no count before the first QZ print", () => {
    const html = orderComplete({ onQzReprint: () => {}, qzCount: 0 });
    expect(html).toContain('title="QZ Print"');
    expect(html).not.toContain(">-0<");
  });

  it("has no QZ button when the POS Profile has QZ printing off", () => {
    expect(orderComplete()).not.toContain('title="QZ Print"');
  });
});
