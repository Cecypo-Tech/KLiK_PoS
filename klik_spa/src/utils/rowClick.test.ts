import { describe, expect, it } from "vitest";
import { clickCameFromControl } from "./rowClick";

// A stand-in for the DOM: each node knows its tag and parent, which is all closest() and
// contains() need.
type FakeNode = { tagName: string; parent: FakeNode | null };

const node = (tagName: string, parent: FakeNode | null = null): FakeNode => ({ tagName, parent });

const asElement = (n: FakeNode): Element =>
  ({
    closest(selector: string) {
      const tags = selector.split(",").map((s) => s.trim().toUpperCase());
      for (let cur: FakeNode | null = n; cur; cur = cur.parent) {
        if (tags.includes(cur.tagName)) return asElement(cur);
      }
      return null;
    },
    contains(other: Element) {
      const target = (other as unknown as { __node: FakeNode }).__node;
      for (let cur: FakeNode | null = target; cur; cur = cur.parent) {
        if (cur === n) return true;
      }
      return false;
    },
    __node: n,
  }) as unknown as Element;

describe("clickCameFromControl", () => {
  const row = node("DIV");

  it("is false for a click on the row's name or icon, so the row toggles", () => {
    const icon = node("DIV", row);
    const name = node("SPAN", row);
    expect(clickCameFromControl(asElement(icon), asElement(row))).toBe(false);
    expect(clickCameFromControl(asElement(name), asElement(row))).toBe(false);
  });

  it("is true for a click in the amount or reference input, so typing never turns the row off", () => {
    const amount = node("INPUT", row);
    expect(clickCameFromControl(asElement(amount), asElement(row))).toBe(true);
  });

  it("is true for a click on the circle's svg, so the button's own toggle is not doubled", () => {
    const circle = node("BUTTON", row);
    const svg = node("SVG", circle);
    expect(clickCameFromControl(asElement(svg), asElement(row))).toBe(true);
  });

  it("ignores a control that wraps the row rather than sitting inside it", () => {
    const outerButton = node("BUTTON");
    const wrappedRow = node("DIV", outerButton);
    const name = node("SPAN", wrappedRow);
    expect(clickCameFromControl(asElement(name), asElement(wrappedRow))).toBe(false);
  });

  it("is false when the target is not an element", () => {
    expect(clickCameFromControl(null, asElement(row))).toBe(false);
  });
});
