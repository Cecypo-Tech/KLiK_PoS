import { describe, expect, it } from "vitest";
import { switchProfileState } from "./switchProfile";

const joined = { entry: "S1", joined: true };
const own = { entry: "S1", joined: false };

describe("switchProfileState", () => {
  it("is hidden for a cashier with one profile", () => {
    expect(switchProfileState({ profileCount: 1, shift: joined, cartCount: 0 })).toEqual({ show: false, blocked: null });
  });

  it("is offered on a joined shift with an empty cart", () => {
    expect(switchProfileState({ profileCount: 2, shift: joined, cartCount: 0 })).toEqual({ show: true, blocked: null });
  });

  it("is offered on a shift the cashier opened: it stays open for whoever is in it", () => {
    expect(switchProfileState({ profileCount: 2, shift: own, cartCount: 0 })).toEqual({ show: true, blocked: null });
  });

  it("is hidden when the cashier is in no shift", () => {
    expect(switchProfileState({ profileCount: 2, shift: { entry: null }, cartCount: 0 }).show).toBe(false);
  });

  it("is blocked while the cart has items", () => {
    expect(switchProfileState({ profileCount: 2, shift: joined, cartCount: 3 }).blocked).toBe("Hold or clear the cart first");
  });

  it("is hidden until the shift is known", () => {
    expect(switchProfileState({ profileCount: 2, shift: null, cartCount: 0 }).show).toBe(false);
  });
});
