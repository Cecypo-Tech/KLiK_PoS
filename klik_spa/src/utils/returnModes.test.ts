import { describe, expect, it } from "vitest";
import { cashRefundModes, defaultCashRefundMode } from "./returnModes";

const modes: Array<{ mode_of_payment: string; type: string; default: number }> = [
  { mode_of_payment: "Mpesa-1", type: "Phone", default: 1 },
  { mode_of_payment: "Card", type: "Bank", default: 0 },
  { mode_of_payment: "Cash", type: "Cash", default: 0 },
  { mode_of_payment: "Petty Cash", type: "Cash", default: 0 },
];

describe("cashRefundModes", () => {
  it("offers only Cash-type modes - card and M-Pesa go back through accounts", () => {
    expect(cashRefundModes(modes).map((m) => m.mode_of_payment)).toEqual(["Cash", "Petty Cash"]);
  });
});

describe("defaultCashRefundMode", () => {
  it("is the till's default mode when that is cash", () => {
    expect(defaultCashRefundMode([{ ...modes[2]!, default: 1 }, modes[3]!])).toBe("Cash");
  });

  it("is the first cash mode when the till's default is not cash", () => {
    expect(defaultCashRefundMode(modes)).toBe("Cash");
  });

  it("is empty when the till has no cash mode", () => {
    expect(defaultCashRefundMode([modes[0]!, modes[1]!])).toBe("");
  });
});
