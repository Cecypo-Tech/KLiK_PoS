import { describe, expect, it } from "vitest";
import {
  addVoucher,
  appliedTotal,
  capVouchers,
  isUsable,
  voucherApplyAmount,
  voucherCustomerRule,
  voucherStatusLabel,
  vouchersBlockedReason,
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
    expect(vouchersBlockedReason({ isCreditSale: false, mpesaOrder: false, editingDraft: false })).toBeNull();
  });

  it("blocks them on a credit sale, an M-Pesa order or an older draft", () => {
    expect(vouchersBlockedReason({ isCreditSale: true, mpesaOrder: false, editingDraft: false })).toMatch(/credit sale/);
    expect(vouchersBlockedReason({ isCreditSale: false, mpesaOrder: true, editingDraft: false })).toMatch(/M-Pesa/);
    expect(vouchersBlockedReason({ isCreditSale: false, mpesaOrder: false, editingDraft: true })).toMatch(/draft/);
  });
});
