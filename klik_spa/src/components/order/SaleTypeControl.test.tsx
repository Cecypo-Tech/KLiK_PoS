import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SaleTypeControl, { type SaleTypeControlProps } from "./SaleTypeControl";

const render = (p: SaleTypeControlProps) => renderToStaticMarkup(<SaleTypeControl {...p} />);

describe("SaleTypeControl", () => {
  it("one radio per option, the value checked", () => {
    const html = render({ value: "credit", options: ["sale", "credit", "quote"], onChange: () => {} });
    expect(html.match(/role="radio"/g)).toHaveLength(3);
    expect(html).toMatch(/aria-checked="true"[^>]*>Credit Sale</);
    expect(html).toMatch(/aria-checked="false"[^>]*>Cash Sale</);
  });

  it("Quote first and on its own, then Cash Sale | Credit Sale as one switch", () => {
    const html = render({ value: "sale", options: ["sale", "credit", "quote"], onChange: () => {} });
    const at = (l: string) => html.indexOf(`>${l}</button>`);
    expect(at("Quote")).toBeLessThan(at("Cash Sale"));
    expect(at("Cash Sale")).toBeLessThan(at("Credit Sale"));
    // Quote's own pill closes before the Cash Sale | Credit Sale switch opens.
    expect(html.slice(at("Quote"), at("Cash Sale"))).toContain("</div>");
    expect(html.slice(at("Cash Sale"), at("Credit Sale"))).not.toContain("</div>");
  });

  it("a disabled reason disables that segment and explains it", () => {
    const html = render({
      value: "sale", options: ["sale", "credit"], onChange: () => {},
      disabledReasons: { credit: "Credit sales need a named customer" },
    });
    expect(html).toContain('title="Credit sales need a named customer"');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Credit Sale</);
  });

  it("renders nothing with a single option", () => {
    expect(render({ value: "sale", options: ["sale"], onChange: () => {} })).toBe("");
  });
});
