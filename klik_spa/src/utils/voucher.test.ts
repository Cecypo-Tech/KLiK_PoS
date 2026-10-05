import { describe, expect, it } from "vitest";
import {
  addVoucher,
  appliedTotal,
  capVouchers,
  customerChangeDropsVouchers,
  isUsable,
  labelVoucherAmounts,
  netOfChange,
  voucherApplyAmount,
  voucherCustomerRule,
  voucherStatusLabel,
  vouchersBlockedReason,
  vouchersLockedByPush,
  resizeVoucher,
} from "./voucher";

const money = (value: number) => `KES ${value.toFixed(2)}`;

describe("voucherStatusLabel", () => {
  it("open shows what is available", () => {
    expect(voucherStatusLabel({ status: "open", available: 510, total: 510 }, money)).toBe("Open: KES 510.00 available");
  });

  it("partly used shows what is left of the whole", () => {
    expect(voucherStatusLabel({ status: "partly_used", available: 60, total: 510 }, money)).toBe(
      "Partly used: KES 60.00 left of KES 510.00",
    );
  });

  it("used, cancelled and no match read plainly", () => {
    expect(voucherStatusLabel({ status: "used" }, money)).toBe("Nothing left (used or refunded)");
    expect(voucherStatusLabel({ status: "cancelled" }, money)).toBe("Cancelled");
    expect(voucherStatusLabel({ status: "no_match" }, money)).toBe("No voucher matches these numbers");
  });
});

describe("isUsable", () => {
  it("only an open or partly used voucher with money left", () => {
    expect(isUsable({ status: "open", available: 10 })).toBe(true);
    expect(isUsable({ status: "partly_used", available: 5 })).toBe(true);
    expect(isUsable({ status: "used", available: 0 })).toBe(false);
    expect(isUsable({ status: "no_match" })).toBe(false);
    expect(isUsable(null)).toBe(false);
  });
});

describe("voucherCustomerRule", () => {
  const walkinSale = { customer: "Walk In", isWalkin: true };
  const namedSale = { customer: "CRN TEST", isWalkin: false };

  it("a voucher pays its owner's sale", () => {
    expect(voucherCustomerRule(namedSale, { customer: "CRN TEST", isWalkin: false })).toBe("apply");
  });

  it("a Walk In voucher pays a Walk In sale", () => {
    expect(voucherCustomerRule(walkinSale, { customer: "Walk In", isWalkin: true })).toBe("apply");
  });

  it("a Walk In sale with a named voucher switches to the owner", () => {
    expect(voucherCustomerRule(walkinSale, { customer: "CRN TEST", isWalkin: false })).toBe("switch");
  });

  it("another named customer's voucher is refused", () => {
    expect(voucherCustomerRule(namedSale, { customer: "OTHER", isWalkin: false })).toBe("refuse_named");
  });

  it("a Walk In voucher never pays a named sale", () => {
    expect(voucherCustomerRule(namedSale, { customer: "Walk In", isWalkin: true })).toBe("refuse_walkin");
  });

  it("a Walk In voucher never pays another Walk In customer's sale", () => {
    expect(voucherCustomerRule(walkinSale, { customer: "Walk In 2", isWalkin: true })).toBe("refuse_walkin");
  });
});

describe("voucherApplyAmount", () => {
  it("takes what the sale still needs, up to what the voucher holds", () => {
    expect(voucherApplyAmount(510, 450, 0)).toBe(450);
    expect(voucherApplyAmount(100, 450, 0)).toBe(100);
  });

  it("counts vouchers already applied", () => {
    expect(voucherApplyAmount(510, 450, 400)).toBe(50);
  });

  it("never goes below zero", () => {
    expect(voucherApplyAmount(510, 450, 450)).toBe(0);
  });
});

describe("addVoucher", () => {
  it("adds a new voucher", () => {
    expect(addVoucher([], { note: "X-POS-1", original: "POS-9", amount: 50 })).toEqual([
      { note: "X-POS-1", original: "POS-9", amount: 50 },
    ]);
  });

  it("never applies the same voucher twice", () => {
    const applied = [{ note: "X-POS-1", original: null, amount: 50 }];
    expect(addVoucher(applied, { note: "X-POS-1", original: null, amount: 20 })).toBe(applied);
  });
});

describe("capVouchers", () => {
  const applied = [
    { note: "A", original: null, amount: 300 },
    { note: "B", original: "S", amount: 200 },
  ];

  it("leaves vouchers that fit alone", () => {
    expect(capVouchers(applied, 600)).toBe(applied);
  });

  it("shrinks the last applied first when the sale gets smaller", () => {
    expect(capVouchers(applied, 400)).toEqual([
      { note: "A", original: null, amount: 300 },
      { note: "B", original: "S", amount: 100 },
    ]);
  });

  it("drops a voucher shrunk to nothing", () => {
    expect(capVouchers(applied, 250)).toEqual([{ note: "A", original: null, amount: 250 }]);
  });
});

describe("appliedTotal", () => {
  it("adds the applied amounts to cents", () => {
    expect(appliedTotal([{ note: "A", original: null, amount: 0.1 }, { note: "B", original: null, amount: 0.2 }])).toBe(0.3);
  });
});

describe("vouchersBlockedReason", () => {
  it("allows vouchers on a normal sale", () => {
    expect(vouchersBlockedReason({ isCreditSale: false, editingDraft: false })).toBeNull();
  });

  it("blocks them on a credit sale or an older draft", () => {
    expect(vouchersBlockedReason({ isCreditSale: true, editingDraft: false })).toMatch(/credit sale/);
    expect(vouchersBlockedReason({ isCreditSale: false, editingDraft: true })).toMatch(/draft/);
  });

  it("names the reason as a bare phrase, to follow the dialog's prefix", () => {
    expect(vouchersBlockedReason({ isCreditSale: true, editingDraft: false })).toBe("this is a credit sale");
    expect(vouchersBlockedReason({ isCreditSale: false, editingDraft: true })).toBe(
      "this sale is finishing an older draft",
    );
  });
});

describe("vouchersLockedByPush", () => {
  it("lets vouchers change before any M-Pesa request", () => {
    expect(vouchersLockedByPush(null)).toBeNull();
  });

  it("refuses once a request went out for what the vouchers left", () => {
    expect(vouchersLockedByPush("Mpesa-1")).toMatch(/before sending the M-Pesa request/);
  });
});

describe("customerChangeDropsVouchers", () => {
  it("keeps them for the first customer the sale has", () => {
    expect(customerChangeDropsVouchers(null, "A", 1)).toBe(false);
  });

  it("keeps them while the customer stays the same", () => {
    expect(customerChangeDropsVouchers("A", "A", 1)).toBe(false);
  });

  it("drops them when the customer changes or is cleared", () => {
    expect(customerChangeDropsVouchers("A", "B", 1)).toBe(true);
    expect(customerChangeDropsVouchers("A", null, 1)).toBe(true);
  });

  it("has nothing to drop without vouchers", () => {
    expect(customerChangeDropsVouchers("A", "B", 0)).toBe(false);
  });

  it("keeps a submitted sale's vouchers when printing empties the cart behind its receipt", () => {
    expect(customerChangeDropsVouchers("A", null, 1, true)).toBe(false);
  });
});

describe("netOfChange", () => {
  const isCash = (method: string) => method === "Cash" || method === "Cash 2";

  it("leaves exact cash alone", () => {
    expect(netOfChange([{ method: "Cash", amount: 150 }], 300, 450, isCash)).toEqual({
      rows: [{ method: "Cash", amount: 150 }],
      unabsorbed: 0,
    });
  });

  it("sends cash net of the change handed back", () => {
    expect(netOfChange([{ method: "Cash", amount: 200 }], 300, 450, isCash)).toEqual({
      rows: [{ method: "Cash", amount: 150 }],
      unabsorbed: 0,
    });
    expect(netOfChange([{ method: "Cash", amount: 0.3 }], 0.1, 0.35, isCash).rows).toEqual([
      { method: "Cash", amount: 0.25 },
    ]);
  });

  it("takes change off the cash row last edited, else the last cash row, then the others", () => {
    const rows = [
      { method: "Cash", amount: 100 },
      { method: "Cash 2", amount: 40 },
    ];
    expect(netOfChange(rows, 350, 450, isCash, "Cash").rows).toEqual([
      { method: "Cash", amount: 60 },
      { method: "Cash 2", amount: 40 },
    ]);
    expect(netOfChange(rows, 350, 450, isCash).rows).toEqual([
      { method: "Cash", amount: 100 },
      { method: "Cash 2", amount: 0 },
    ]);
    expect(netOfChange(rows, 370, 450, isCash).rows).toEqual([
      { method: "Cash", amount: 80 },
      { method: "Cash 2", amount: 0 },
    ]);
  });

  it("reports an overpay no cash row can absorb", () => {
    expect(netOfChange([{ method: "Card", amount: 200 }], 300, 450, isCash)).toEqual({
      rows: [{ method: "Card", amount: 200 }],
      unabsorbed: 50,
    });
    expect(
      netOfChange(
        [
          { method: "Cash", amount: 20 },
          { method: "Card", amount: 200 },
        ],
        300,
        450,
        isCash,
      ),
    ).toEqual({
      rows: [
        { method: "Cash", amount: 0 },
        { method: "Card", amount: 200 },
      ],
      unabsorbed: 50,
    });
  });

  it("changes nothing without vouchers - ERPNext books that change itself", () => {
    const rows = [{ method: "Cash", amount: 500 }];
    expect(netOfChange(rows, 0, 450, isCash)).toEqual({ rows, unabsorbed: 0 });
  });
});

describe("labelVoucherAmounts", () => {
  it("shows the vouchers' total as Vouchers", () => {
    expect(labelVoucherAmounts({ Cash: 150, __v__: 300 }, "__v__")).toEqual({ Cash: 150, Vouchers: 300 });
  });

  it("leaves amounts without vouchers alone", () => {
    const amounts = { Cash: 450 };
    expect(labelVoucherAmounts(amounts, "__v__")).toBe(amounts);
  });

  it("never hides a real mode named Vouchers", () => {
    expect(labelVoucherAmounts({ Vouchers: 50, __v__: 300 }, "__v__")).toEqual({
      Vouchers: 50,
      "Vouchers (store credit)": 300,
    });
  });
});

describe("resizeVoucher", () => {
  const applied = [
    { note: "CN-1", original: null, amount: 300, available: 2100 },
    { note: "CN-2", original: null, amount: 200, available: 200 },
  ];

  it("spends part of a voucher", () => {
    expect(resizeVoucher(applied, "CN-1", 100, 1000)[0].amount).toBe(100);
  });

  it("never spends more than the voucher holds", () => {
    expect(resizeVoucher(applied, "CN-2", 500, 5000)[1].amount).toBe(200);
  });

  it("never pays more than the sale still owes after the other vouchers", () => {
    expect(resizeVoucher(applied, "CN-1", 2000, 1000)[0].amount).toBe(800);
  });

  it("drops a voucher set to nothing, and leaves the others alone", () => {
    expect(resizeVoucher(applied, "CN-1", 0, 1000)).toEqual([applied[1]]);
  });

  it("caps at the amount first applied when the balance is unknown", () => {
    const old = [{ note: "CN-3", original: null, amount: 50 }];
    expect(resizeVoucher(old, "CN-3", 80, 1000)[0].amount).toBe(50);
  });
});
