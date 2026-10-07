import { describe, expect, it, vi } from "vitest";

import { blockKey } from "./blockKey";

const press = (key: string) => ({ key, preventDefault: vi.fn(), stopImmediatePropagation: vi.fn() });

describe("blockKey", () => {
  it("stops the key before the POS's own listeners see it", () => {
    const event = press("F4");
    blockKey("F4")(event);
    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.stopImmediatePropagation).toHaveBeenCalled();
  });

  it("lets every other key through", () => {
    const event = press("Enter");
    blockKey("F4")(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(event.stopImmediatePropagation).not.toHaveBeenCalled();
  });
});
