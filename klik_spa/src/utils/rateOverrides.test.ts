import { describe, expect, it } from "vitest";

import { consumeRateOverrides, enqueueRateOverride } from "./rateOverrides";

describe("rate override queue", () => {
  it("keeps every request in order, so several lines' rates all apply", () => {
    let state = enqueueRateOverride([], 0, { itemId: "A", rate: 150, includesTax: false });
    state = enqueueRateOverride(state.queue, state.nonce, { itemId: "B", rate: 220, includesTax: true });
    expect(state.queue).toEqual([
      { itemId: "A", rate: 150, includesTax: false, nonce: 1 },
      { itemId: "B", rate: 220, includesTax: true, nonce: 2 },
    ]);
  });

  it("drops what was applied and keeps numbering after it", () => {
    let state = enqueueRateOverride([], 0, { itemId: "A", rate: 150, includesTax: false });
    state = enqueueRateOverride(state.queue, state.nonce, { itemId: "B", rate: 220, includesTax: false });
    const rest = consumeRateOverrides(state.queue, 1);
    expect(rest.map((o) => o.itemId)).toEqual(["B"]);
    const next = enqueueRateOverride(consumeRateOverrides(rest, 2), state.nonce, { itemId: "A", rate: 1, includesTax: false });
    expect(next.queue).toEqual([{ itemId: "A", rate: 1, includesTax: false, nonce: 3 }]);
  });
});
