import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import KeyboardShortcutsPanel from "./KeyboardShortcutsPanel";

const render = (mode?: "grid") =>
  renderToStaticMarkup(<KeyboardShortcutsPanel isOpen onClose={() => {}} mode={mode} />);

describe("KeyboardShortcutsPanel", () => {
  it("grid mode lists the line grid keys and hides the product list", () => {
    const html = render("grid");
    expect(html).toContain("Line grid");
    for (const key of [">F3<", ">F8<", ">Shift<", ">Delete<", ">Alt<", ">D<"]) expect(html).toContain(key);
    expect(html).not.toContain("Product List");
  });

  it("default mode is unchanged: product list shown, no line grid group", () => {
    const html = render();
    expect(html).toContain("Product List");
    expect(html).not.toContain("Line grid");
  });
});
