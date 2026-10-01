import { describe, expect, it } from "vitest";
import { bankingError, closingBalancePayload, floatModeNames, leftInDrawer } from "./closingBanking";

describe("leftInDrawer", () => {
  it("is the count less what goes to the bank", () => {
    expect(leftInDrawer(100000, 95000)).toBe(5000);
    expect(leftInDrawer(1000, 0)).toBe(1000);
  });
  it("rounds to cents", () => {
    expect(leftInDrawer(100.3, 0.1)).toBe(100.2);
  });
});

describe("bankingError", () => {
  it("is null for a figure within the count", () => {
    expect(bankingError(100000, 95000)).toBeNull();
    expect(bankingError(100000, 100000)).toBeNull();
    expect(bankingError(0, 0)).toBeNull();
  });
  it("refuses banking more than was counted", () => {
    expect(bankingError(100000, 150000)).toMatch(/more than was counted/);
  });
  it("refuses a negative figure", () => {
    expect(bankingError(100, -1)).toMatch(/negative/);
  });
});

describe("closingBalancePayload", () => {
  const floats = new Set(["Cash"]);
  it("sends banking for float modes only", () => {
    expect(
      closingBalancePayload({ Cash: 100000, "Mpesa-1": 40000 }, { Cash: 95000, "Mpesa-1": 500 }, floats),
    ).toEqual([
      { mode_of_payment: "Cash", closing_amount: 100000, banked_amount: 95000 },
      { mode_of_payment: "Mpesa-1", closing_amount: 40000 },
    ]);
  });
  it("leaves banked_amount off when nothing is banked", () => {
    expect(closingBalancePayload({ Cash: 300 }, {}, floats)).toEqual([{ mode_of_payment: "Cash", closing_amount: 300 }]);
  });
});

describe("floatModeNames", () => {
  it("is the Cash-type modes, by either name key", () => {
    expect(
      floatModeNames([
        { mode_of_payment: "Cash", type: "Cash" },
        { mode_of_payment: "Cheque", type: "Bank" },
        { name: "Till Float", mode_of_payment: "Till Float", type: "Cash" },
      ]),
    ).toEqual(new Set(["Cash", "Till Float"]));
  });
});
