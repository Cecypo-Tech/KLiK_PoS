import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import QzRulePicker from "./QzRulePicker";

const render = (open: boolean) =>
  renderToStaticMarkup(
    <QzRulePicker
      open={open}
      options={[
        { rule: "Invoice", limit_reached: false },
        { rule: "Packing List", limit_reached: true },
      ]}
      onConfirm={() => {}}
      onCancel={() => {}}
    />,
  );

describe("QzRulePicker", () => {
  it("lists the rules in order, ticked unless at their print limit", () => {
    const html = render(true);
    expect(html).toContain("Print via QZ");
    expect(html.indexOf("Invoice")).toBeLessThan(html.indexOf("Packing List"));
    expect(html).toContain("Packing List (limit reached)");
    expect(html.match(/checked=""/g)?.length).toBe(1);
  });

  it("renders nothing while closed", () => {
    expect(render(false)).toBe("");
  });
});
