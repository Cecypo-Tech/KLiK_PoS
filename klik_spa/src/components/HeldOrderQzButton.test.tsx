import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import HeldOrderQzButton from "./HeldOrderQzButton";

// Resolves from the repo-root node_modules, which has no react.
vi.mock("react-toastify", () => ({ toast: {} }));

describe("HeldOrderQzButton", () => {
  it("renders the QZ button, picker closed", () => {
    const html = renderToStaticMarkup(<HeldOrderQzButton orderId="SAL-ORD-1" className="p-1" iconSize={16} />);
    expect(html).toContain('aria-label="QZ Print"');
    expect(html).not.toContain("Print via QZ");
    expect(html).not.toContain("disabled");
  });

  it("shows disabled, saying why, when the till blocks printing held orders", () => {
    const html = renderToStaticMarkup(
      <HeldOrderQzButton orderId="SAL-ORD-1" className="p-1" iconSize={16} blockedTitle="Blocked here" />,
    );
    expect(html).toContain('aria-label="QZ Print"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('title="Blocked here"');
  });
});
