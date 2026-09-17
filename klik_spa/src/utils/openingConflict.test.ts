import { describe, expect, it } from "vitest";
import { conflictNotice, type OpeningConflict } from "./openingConflict";

const conflict = (kind: OpeningConflict["kind"]): OpeningConflict => ({
  kind,
  entry: "POS-OPE-2026-00024",
  pos_profile: "_Test POS Profile",
  period_start_date: "2026-09-14 22:17:56",
  user: "cashier@example.com",
  user_name: "Cashier",
});

describe("conflictNotice", () => {
  it("offers to carry on in a shift already open today on this till", () => {
    const notice = conflictNotice(conflict("own_open"));
    expect(notice.action).toBe("continue");
    expect(notice.message).toContain("POS-OPE-2026-00024");
  });

  it("sends a shift left open from an earlier day to closing", () => {
    const notice = conflictNotice(conflict("own_stale"));
    expect(notice.action).toBe("close");
    expect(notice.message).toContain("earlier day");
  });

  it("sends a shift open on another till to closing, naming that till", () => {
    const notice = conflictNotice(conflict("own_other_profile"));
    expect(notice.action).toBe("close");
    expect(notice.message).toContain("_Test POS Profile");
  });

  it("offers to join another cashier's shift on this till", () => {
    const notice = conflictNotice({ ...conflict("till_open"), user_name: "Derrick" });
    expect(notice.action).toBe("join");
    expect(notice.message).toContain("Derrick");
  });

  it("offers to join and close a shift left open from an earlier day", () => {
    expect(conflictNotice(conflict("till_stale")).action).toBe("join_close");
  });

  it("tells a cashier a manager is needed for a single stale shift, naming it", () => {
    const notice = conflictNotice({
      ...conflict("till_needs_manager"),
      manager: false,
      open_shifts: [
        {
          entry: "POS-OPE-2026-00024",
          user: "cashier@example.com",
          user_name: "Cashier",
          period_start_date: "2026-09-14 22:17:56",
          stale: true,
        },
      ],
    });
    expect(notice.action).toBe("none");
    expect(notice.message).toContain("POS-OPE-2026-00024");
    expect(notice.message).toContain("Cashier");
  });

  it("shows only the date a single stale shift was opened, not the time", () => {
    const notice = conflictNotice({
      ...conflict("till_needs_manager"),
      manager: false,
      open_shifts: [
        {
          entry: "POS-OPE-2026-00024",
          user: "cashier@example.com",
          user_name: "Cashier",
          period_start_date: "2026-09-14 22:17:56",
          stale: true,
        },
      ],
    });
    expect(notice.message).toContain("2026-09-14");
    expect(notice.message).not.toContain("22:17:56");
  });

  it("tells a cashier a manager is needed for several open shifts, naming the count", () => {
    const notice = conflictNotice({
      ...conflict("till_needs_manager"),
      manager: false,
      open_shifts: [
        {
          entry: "POS-OPE-2026-00024",
          user: "cashier@example.com",
          user_name: "Cashier",
          period_start_date: "2026-09-14 22:17:56",
          stale: true,
        },
        {
          entry: "POS-OPE-2026-00025",
          user: "other@example.com",
          user_name: "Other",
          period_start_date: "2026-09-17 08:00:00",
          stale: false,
        },
      ],
    });
    expect(notice.action).toBe("none");
    expect(notice.message).toContain("2");
  });

  it("offers a manager the extra shifts to close, one by one", () => {
    const notice = conflictNotice({
      ...conflict("till_multiple"),
      manager: true,
      open_shifts: [
        {
          entry: "POS-OPE-2026-00024",
          user: "cashier@example.com",
          user_name: "Cashier",
          period_start_date: "2026-09-14 22:17:56",
          stale: true,
        },
        {
          entry: "POS-OPE-2026-00025",
          user: "other@example.com",
          user_name: "Other",
          period_start_date: "2026-09-17 08:00:00",
          stale: false,
        },
      ],
    });
    expect(notice.action).toBe("close_each");
  });
});
