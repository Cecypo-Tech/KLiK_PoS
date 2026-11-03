import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import PriceFloorPanel from "./PriceFloorPanel";

vi.mock("react-toastify", () => ({ toast: {} }));

const floor = { enforced: true, rows: [{ idx: 1, item_code: "B", item_name: "Bulb", uom: "Nos", qty: 1, rate: 400, minimum: 450, price_list: "Retail" }] };
const render = (noApprovers?: boolean) =>
  renderToStaticMarkup(
    <PriceFloorPanel
      floor={floor}
      authorisation={null}
      getPreviewPayload={() => null}
      formatMoney={(v) => String(v)}
      onAuthorised={() => {}}
      onFixPrices={() => {}}
      onAskManager={() => {}}
      noApprovers={noApprovers}
    />,
  );

describe("PriceFloorPanel", () => {
  it("offers Authorise and Ask manager", () => {
    const html = render(false);
    expect(html).not.toContain(`disabled=""`);
    expect(html).not.toContain("No approvers");
  });

  it("shows them disabled, saying why, where nobody can approve", () => {
    const html = render(true);
    expect(html.match(/disabled=""/g)?.length).toBe(2); // Authorise and Ask manager; Fix prices stays
    expect(html).toContain("No approvers are set up");
  });
});
