import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import CreditSaleCard from "./CreditSaleCard";

const base = {
  customerName: "JOHN NJENGA MUIRURI",
  termsTemplate: "",
  onSelectTerm: () => {},
  dueDate: "",
  onDueDateChange: () => {},
  disabled: false,
  currencySymbol: "KES",
};

describe("CreditSaleCard", () => {
  it("terms on the site: the terms picker, no date field", () => {
    const html = renderToStaticMarkup(
      <CreditSaleCard {...base} terms={{ templates: [{ name: "Net 30", due_date: "2026-12-13" }], default: "Net 30" }} />,
    );
    expect(html).toContain('id="pos-credit-terms"');
    expect(html).not.toContain("pos-credit-due-date");
    expect(html).toContain("Net 30 - due 13 Dec 2026");
    expect(html).toContain("JOHN NJENGA MUIRURI");
  });

  it("no terms: the date field", () => {
    const html = renderToStaticMarkup(<CreditSaleCard {...base} terms={null} />);
    expect(html).toContain('id="pos-credit-due-date"');
    expect(html).not.toContain("pos-credit-terms");
  });
});
