import { describe, expect, it } from "vitest";

import { chooseTerm, termLabel, type CreditTerms } from "./creditTerms";

const terms: CreditTerms = {
  templates: [
    { name: "7 Days", due_date: "2026-10-09" },
    { name: "30 Days", due_date: "2026-11-01" },
  ],
  default: "30 Days",
};

describe("chooseTerm", () => {
  it("preselects the server's default", () => {
    expect(chooseTerm(terms, "")).toEqual({ name: "30 Days", due_date: "2026-11-01" });
  });

  it("keeps the cashier's pick while it is still offered", () => {
    expect(chooseTerm(terms, "7 Days")?.name).toBe("7 Days");
  });

  it("falls back to the default when the pick is gone (another customer's list)", () => {
    expect(chooseTerm(terms, "60 Days")?.name).toBe("30 Days");
  });

  it("falls back to the earliest when the default is missing", () => {
    expect(chooseTerm({ ...terms, default: null }, "")?.name).toBe("7 Days");
  });

  it("has nothing to choose without templates: the till keeps its date field", () => {
    expect(chooseTerm({ templates: [], default: null }, "")).toBeNull();
    expect(chooseTerm(null, "")).toBeNull();
  });
});

describe("termLabel", () => {
  it("names the terms and the date they give", () => {
    expect(termLabel({ name: "30 Days", due_date: "2026-11-01" })).toBe("30 Days - due 01 Nov 2026");
  });
});
