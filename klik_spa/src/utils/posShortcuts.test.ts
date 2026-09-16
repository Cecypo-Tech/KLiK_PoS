import { describe, expect, it, vi } from "vitest";
import { createShortcutRegistry, isF10 } from "./posShortcuts";

const key = (key: string, shiftKey = false) => ({ key, shiftKey });

describe("isF10", () => {
  it("matches F10 with or without Shift, and nothing else", () => {
    expect(isF10(key("F10"))).toBe(true);
    expect(isF10(key("F10", true))).toBe(true);
    expect(isF10(key("F9"))).toBe(false);
  });
});

describe("shortcut registry", () => {
  it("sends F10 to the top layer only, so an open dialog never also fires the cart", () => {
    const registry = createShortcutRegistry();
    const cart = { f10: vi.fn(), shiftF10: vi.fn() };
    const dialog = { f10: vi.fn(), shiftF10: vi.fn() };
    registry.push(cart);
    registry.push(dialog);

    registry.dispatch(key("F10"));
    registry.dispatch(key("F10", true));

    expect(dialog.f10).toHaveBeenCalledTimes(1);
    expect(dialog.shiftF10).toHaveBeenCalledTimes(1);
    expect(cart.f10).not.toHaveBeenCalled();
    expect(cart.shiftF10).not.toHaveBeenCalled();
  });

  it("falls back to the layer below once the top one is removed", () => {
    const registry = createShortcutRegistry();
    const cart = { f10: vi.fn() };
    registry.push(cart);
    const removeDialog = registry.push({ f10: vi.fn() });

    removeDialog();
    registry.dispatch(key("F10"));

    expect(cart.f10).toHaveBeenCalledTimes(1);
  });

  it("removes the right layer even when layers close out of order", () => {
    const registry = createShortcutRegistry();
    const removeFirst = registry.push({ f10: vi.fn() });
    const second = { f10: vi.fn() };
    registry.push(second);

    removeFirst();
    registry.dispatch(key("F10"));

    expect(second.f10).toHaveBeenCalledTimes(1);
  });

  it("does nothing, without throwing, when the top layer has no handler for the key", () => {
    const registry = createShortcutRegistry();
    const below = { shiftF10: vi.fn() };
    registry.push(below);
    registry.push({ f10: vi.fn() });

    expect(() => registry.dispatch(key("F10", true))).not.toThrow();
    expect(below.shiftF10).not.toHaveBeenCalled();
  });

  it("claims F10 as handled even with no layers, so the browser's menu bar never takes it", () => {
    const registry = createShortcutRegistry();
    expect(registry.dispatch(key("F10"))).toBe(true);
    expect(registry.dispatch(key("Enter"))).toBe(false);
  });
});

describe("installPosShortcutListener", () => {
  it("cancels every F10, repeats and keyup included, and dispatches one press once", async () => {
    vi.resetModules();
    const listeners: Record<string, (e: unknown) => void> = {};
    vi.stubGlobal("window", {
      addEventListener: (type: string, fn: (e: unknown) => void, opts: { capture?: boolean }) => {
        expect(opts?.capture).toBe(true);
        listeners[type] = fn;
      },
    });
    const mod = await import("./posShortcuts");
    mod.installPosShortcutListener();
    mod.installPosShortcutListener();
    const f10 = vi.fn();
    mod.posShortcuts.push({ f10 });

    const event = (repeat = false, k = "F10") => ({ key: k, shiftKey: false, repeat, preventDefault: vi.fn() });
    const press = event();
    const held = event(true);
    const release = event();
    const other = event(false, "Enter");
    const keydown = listeners.keydown!;
    const keyup = listeners.keyup!;
    keydown(press);
    keydown(held);
    keyup(release);
    keydown(other);

    expect(press.preventDefault).toHaveBeenCalled();
    expect(held.preventDefault).toHaveBeenCalled();
    expect(release.preventDefault).toHaveBeenCalled();
    expect(other.preventDefault).not.toHaveBeenCalled();
    expect(f10).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
