import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { NumberField } from "./NumberField";

const html = (props: Partial<Parameters<typeof NumberField>[0]>) =>
  renderToStaticMarkup(<NumberField value={0} kind="money" onCommit={() => {}} {...props} />);

describe("NumberField at rest", () => {
  it("shows money formatted", () => {
    expect(html({ value: 14500, kind: "money" })).toContain('value="14,500.00"');
  });
  it("shows a quantity with its own decimals", () => {
    expect(html({ value: 2.5, kind: "qty" })).toContain('value="2.5"');
  });
  it("is a text box, so a sum can be typed", () => {
    const out = html({ value: 1, kind: "qty" });
    expect(out).toContain('type="text"');
    expect(out).toContain('inputMode="decimal"');
  });
  it("leaves 0 blank when asked, so the placeholder shows", () => {
    expect(html({ value: 0, blankZero: true, placeholder: "0.00" })).toContain('value=""');
  });
});
