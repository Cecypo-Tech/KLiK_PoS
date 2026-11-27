import { describe, expect, it } from "vitest";

import { extractErrorMessage } from "./errorExtraction";

describe("extractErrorMessage", () => {
  it("tells the till to hold the order when powerpack asks for a price approval", () => {
    const message = "Row(s) 1 are below the minimum selling price. Use <b>Request Price Approval</b> before submitting.";
    expect(extractErrorMessage({ message })).toBe(
      "Row(s) 1 are below the minimum selling price. Hold the order, then use Request Price Approval in History > Held."
    );
  });

  it("keeps line breaks and list items apart when it strips the server's HTML", () => {
    const message =
      "Credit limit has been crossed (3200.0/1000.0)<br><br>Please contact:<br><br><ul><li>kushal (k@x.com)<li>mathias (m@x.com)</li></ul><br>Hold the order instead.";
    expect(extractErrorMessage({ message })).toBe(
      "Credit limit has been crossed (3200.0/1000.0). Please contact: kushal (k@x.com), mathias (m@x.com). Hold the order instead."
    );
  });
});

describe("server messages carry HTML entities", () => {
  it("decodes them after stripping tags (cecypo_powerpack's price floor)", () => {
    const msg = "Row #1 (FITCH &amp; LEEDES CLASSIC GINGER BEER300ML): Net selling rate should be at least <strong>521.28</strong>.";
    expect(extractErrorMessage({ message: msg })).toBe(
      "Row #1 (FITCH & LEEDES CLASSIC GINGER BEER300ML): Net selling rate should be at least 521.28.",
    );
  });
  it("decodes quotes, angle brackets, numeric entities and nbsp, once only", () => {
    expect(extractErrorMessage({ message: "&quot;A&quot; &#39;B&#x27; &lt;5&gt;&nbsp;x &amp;amp;" })).toBe(`"A" 'B' <5> x &amp;`);
  });
});
