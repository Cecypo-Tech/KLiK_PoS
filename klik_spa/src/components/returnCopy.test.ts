import { describe, expect, it } from "vitest";
import { creditNoteLine, processReturnLabel } from "./returnCopy";

describe("return window copy", () => {
  it("names the total on the button", () => {
    expect(processReturnLabel(150400, "KES", false)).toBe("Process Return · KES 150,400.00");
    expect(processReturnLabel(150400, "KES", true)).toBe("Processing Return...");
  });
  it("credit note line: owed on the sale", () => {
    expect(creditNoteLine(2500, 10000, "KES")).toBe("KES 2,500.00 comes off what the customer owes on this sale.");
  });
  it("credit note line: otherwise customer credit", () => {
    expect(creditNoteLine(150400, 0, "KES")).toBe("KES 150,400.00 stays as customer credit. Card/M-Pesa refunds go through accounts.");
    expect(creditNoteLine(15000, 10000, "KES")).toBe("KES 15,000.00 stays as customer credit. Card/M-Pesa refunds go through accounts.");
  });
});
