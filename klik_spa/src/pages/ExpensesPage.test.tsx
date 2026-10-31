import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { ExpenseForm, ExpenseList } from "./ExpensesPage";

vi.mock("react-toastify", () => ({ toast: {} }));

describe("ExpenseForm", () => {
  it("renders the type select, amount, note and Save", () => {
    const html = renderToStaticMarkup(
      <ExpenseForm types={[{ label: "Fuel" }, { label: "Cleaning" }]} saving={false} onSave={async () => true} />,
    );
    expect(html).toContain("<option");
    expect(html).toContain("Fuel");
    expect(html).toContain("Cleaning");
    expect(html).toContain('inputMode="decimal"');
    expect(html).toContain('name="note"');
    expect(html).toContain("Save");
  });

  it("disables Save while empty, and while saving", () => {
    const html = renderToStaticMarkup(<ExpenseForm types={[{ label: "Fuel" }]} saving={false} onSave={async () => true} />);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Save/);
    const saving = renderToStaticMarkup(<ExpenseForm types={[{ label: "Fuel" }]} saving onSave={async () => true} />);
    expect(saving).toMatch(/<button[^>]*disabled=""/);
  });
});

describe("ExpenseList", () => {
  const rows = [
    { name: "J1", label: "Fuel", note: "van", amount: 10, owner: "a@x.com", docstatus: 0, creation: "2026-10-31 09:00:00" },
    { name: "J2", label: "Tea", note: "", amount: 2, owner: "b@x.com", docstatus: 1, creation: "2026-10-31 10:00:00" },
  ];

  it("marks drafts as awaiting approval", () => {
    const html = renderToStaticMarkup(<ExpenseList rows={rows} qz={false} />);
    expect(html).toContain("Fuel");
    expect(html).toContain("Awaiting approval");
    expect(html.match(/Awaiting approval/g)).toHaveLength(1);
    expect(html).not.toContain('aria-label="QZ Print"');
  });

  it("shows a QZ button per row when the profile prints via QZ", () => {
    const html = renderToStaticMarkup(<ExpenseList rows={rows} qz />);
    expect(html.match(/aria-label="QZ Print"/g)).toHaveLength(2);
  });
});

describe("navigation", () => {
  const render = async (can: boolean | undefined) => {
    vi.resetModules();
    vi.doMock("../hooks/useUserInfo", () => ({ useUserInfo: () => ({ userInfo: { can_record_expenses: can } }) }));
    vi.doMock("../stores/posProfileStore", () => ({ usePOSProfileStore: () => ({ posDetails: {} }) }));
    const { default: Sidebar } = await import("../components/RetailSidebar");
    const { default: Bottom } = await import("../components/BottomNavigation");
    return renderToStaticMarkup(<MemoryRouter><Sidebar /><Bottom /></MemoryRouter>);
  };

  it("hides Expenses unless can_record_expenses is true", async () => {
    expect(await render(false)).not.toContain('title="Expenses"');
    expect(await render(undefined)).not.toContain('title="Expenses"');
    expect(await render(true)).toContain('title="Expenses"');
  });
});
