import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SaleTypeControl, { type SaleTypeControlProps } from "./SaleTypeControl";

const render = (p: SaleTypeControlProps) => renderToStaticMarkup(<SaleTypeControl {...p} />);

describe("SaleTypeControl", () => {
  it("one radio per option, the value checked", () => {
    const html = render({ value: "credit", options: ["sale", "credit", "quote"], onChange: () => {} });
    expect(html.match(/role="radio"/g)).toHaveLength(3);
    expect(html).toMatch(/aria-checked="true"[^>]*>Credit</);
    expect(html).toMatch(/aria-checked="false"[^>]*>Sale</);
  });

  it("a disabled reason disables that segment and explains it", () => {
    const html = render({
      value: "sale", options: ["sale", "credit"], onChange: () => {},
      disabledReasons: { credit: "Credit sales need a named customer" },
    });
    expect(html).toContain('title="Credit sales need a named customer"');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Credit</);
  });

  it("renders nothing with a single option", () => {
    expect(render({ value: "sale", options: ["sale"], onChange: () => {} })).toBe("");
  });
});
