import { describe, expect, it } from "vitest";
import { approvalAnswers, PENDING } from "./approvalWatch";

const row = (name: string, approval_state: string | null, owner = "me@x") => ({ name, approval_state, owner, customer_name: "Walk In" });

describe("approvalAnswers", () => {
  it("reports my pending orders a manager approved or declined", () => {
    const before = new Set(["SO-1", "SO-2", "SO-3"]);
    const { approved, declined, pending } = approvalAnswers(before, [
      row("SO-1", "Price Approved"),
      row("SO-2", "Draft"),
      row("SO-3", PENDING),
    ], "me@x");
    expect(approved.map((r) => r.name)).toEqual(["SO-1"]);
    expect(declined.map((r) => r.name)).toEqual(["SO-2"]);
    expect([...pending]).toEqual(["SO-3"]);
  });

  it("says nothing about orders it never saw pending, checked-out orders or other cashiers' orders", () => {
    const { approved, declined, pending } = approvalAnswers(new Set(["SO-gone"]), [
      row("SO-1", "Price Approved"),
      row("SO-9", PENDING, "other@x"),
    ], "me@x");
    expect(approved).toEqual([]);
    expect(declined).toEqual([]);
    expect([...pending]).toEqual([]);
  });
});
