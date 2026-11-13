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

  it("shows what the customer owes when a balance is given", () => {
    const html = renderToStaticMarkup(<CreditSaleCard {...base} terms={null} balance={{ customer: "C1", outstanding: 5000, overdue: 2000 }} />);
    expect(html).toContain("Owes KES 5,000.00");
    expect(html).toContain("KES 2,000.00 overdue");
  });

  it("no balance line without a balance", () => {
    const html = renderToStaticMarkup(<CreditSaleCard {...base} terms={null} />);
    expect(html).not.toContain("Owes");
  });
});
