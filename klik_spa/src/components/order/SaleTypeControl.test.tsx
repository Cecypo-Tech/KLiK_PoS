import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SaleTypeControl, { type SaleTypeControlProps } from "./SaleTypeControl";

const render = (p: SaleTypeControlProps) => renderToStaticMarkup(<SaleTypeControl {...p} />);

describe("SaleTypeControl", () => {
  it("one dropdown, one option per type, the value selected", () => {
    const html = render({ value: "credit", options: ["sale", "credit", "quote"], onChange: () => {} });
    expect(html.match(/<select/g)).toHaveLength(1);
    expect(html.match(/<option/g)).toHaveLength(3);
    expect(html).toMatch(/<option value="credit"[^>]*selected=""[^>]*>Credit Sale</);
  });

  it("orders Quote, Cash Sale, Credit Sale whatever order it is given", () => {
    const html = render({ value: "sale", options: ["sale", "credit", "quote"], onChange: () => {} });
    const at = (l: string) => html.indexOf(`>${l}</option>`);
    expect(at("Quote")).toBeLessThan(at("Cash Sale"));
    expect(at("Cash Sale")).toBeLessThan(at("Credit Sale"));
  });

  it("colours the box by the chosen type", () => {
    expect(render({ value: "quote", options: ["sale", "quote"], onChange: () => {} })).toContain("bg-amber-600");
    expect(render({ value: "credit", options: ["sale", "credit"], onChange: () => {} })).toContain("bg-teal-600");
  });

  it("a disabled reason disables that option and says why", () => {
    const html = render({
      value: "sale", options: ["sale", "credit"], onChange: () => {},
      disabledReasons: { credit: "Credit sales need a named customer" },
    });
    expect(html).toMatch(/<option value="credit"[^>]*disabled=""[^>]*>Credit Sale — Credit sales need a named customer</);
  });

  it("renders nothing with a single option", () => {
    expect(render({ value: "sale", options: ["sale"], onChange: () => {} })).toBe("");
  });
});
