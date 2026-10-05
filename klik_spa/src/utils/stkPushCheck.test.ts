import { describe, expect, it } from "vitest";
import { AUTO_CHECK_EVERY_MS, AUTO_CHECK_FIRST_MS, autoCheckDelay, pushCheckMessage } from "./stkPushCheck";

const waiting = { source: "stk" as const, status: "in_progress" as const, requestName: "MEXP-1" };

describe("autoCheckDelay", () => {
  it("first asks Safaricom 20 s into the wait, then every 15 s", () => {
    expect(AUTO_CHECK_FIRST_MS).toBe(20_000);
    expect(AUTO_CHECK_EVERY_MS).toBe(15_000);
    expect(autoCheckDelay(waiting, null)).toBe(AUTO_CHECK_FIRST_MS);
    expect(autoCheckDelay(waiting, "MEXP-1")).toBe(AUTO_CHECK_EVERY_MS);
  });

  it("a new push starts again at 20 s", () => {
    expect(autoCheckDelay(waiting, "MEXP-0")).toBe(AUTO_CHECK_FIRST_MS);
  });

  it("asks nothing for an answered push, or picked receipts", () => {
    expect(autoCheckDelay({ ...waiting, status: "completed" }, null)).toBeNull();
    expect(autoCheckDelay({ ...waiting, status: "failed" }, null)).toBeNull();
    expect(autoCheckDelay({ source: "c2b", status: "in_progress" }, null)).toBeNull();
    expect(autoCheckDelay(null, null)).toBeNull();
  });
});

describe("pushCheckMessage", () => {
  it("says what Safaricom answered", () => {
    expect(pushCheckMessage({ outcome: "paid" })).toBe("Payment confirmed");
    expect(pushCheckMessage({ outcome: "paid", transaction_id: "UJ1TEST" })).toBe("Payment confirmed");
    expect(pushCheckMessage({ outcome: "not_paid", reason: "Request cancelled by user" })).toBe("Request cancelled by user");
    expect(pushCheckMessage({ outcome: "waiting" })).toBe("The customer is still being asked - check again shortly.");
    expect(pushCheckMessage({ outcome: "no_answer" })).toBe("Couldn't get an answer from Safaricom - try again.");
  });
});
