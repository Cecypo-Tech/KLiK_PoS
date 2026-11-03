import { describe, expect, it } from "vitest";

import { extractErrorMessage } from "./errorExtraction";

describe("extractErrorMessage", () => {
  it("keeps line breaks and list items apart when it strips the server's HTML", () => {
    const message =
      "Credit limit has been crossed (3200.0/1000.0)<br><br>Please contact:<br><br><ul><li>kushal (k@x.com)<li>mathias (m@x.com)</li></ul><br>Hold the order instead.";
    expect(extractErrorMessage({ message })).toBe(
      "Credit limit has been crossed (3200.0/1000.0). Please contact: kushal (k@x.com), mathias (m@x.com). Hold the order instead."
    );
  });
});
