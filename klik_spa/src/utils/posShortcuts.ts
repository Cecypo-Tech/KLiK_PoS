/**
 * F10 / Shift+F10 on the POS screens.
 *
 * Firefox on Windows and Linux toggles its menu bar on a bare F10 unless the page
 * cancels the keydown, and while the menu bar is active the page gets no keys at all -
 * so an F10 nobody cancelled was lost, and so was the next one. One capture-phase
 * listener therefore cancels every F10, whatever is mounted.
 *
 * Several components want F10 (the cart's Checkout, the payment dialog's Submit), and
 * each listening on document meant one press fired all of them. Instead each registers
 * a layer; only the most recent one handles the key.
 */

export interface ShortcutLayer {
  f10?: () => void;
  shiftF10?: () => void;
}

interface KeyLike {
  key: string;
  shiftKey: boolean;
}

export function isF10(e: KeyLike): boolean {
  return e.key === "F10";
}

export function createShortcutRegistry() {
  const layers: { layer: ShortcutLayer }[] = [];

  return {
    /** Adds a layer on top; the returned function removes exactly that layer. */
    push(layer: ShortcutLayer): () => void {
      const entry = { layer };
      layers.push(entry);
      return () => {
        const at = layers.indexOf(entry);
        if (at >= 0) layers.splice(at, 1);
      };
    },
    /** Runs the top layer's handler. True when the key is an F10 the page owns. */
    dispatch(e: KeyLike): boolean {
      if (!isF10(e)) return false;
      const top = layers[layers.length - 1]?.layer;
      const handler = e.shiftKey ? top?.shiftF10 : top?.f10;
      handler?.();
      return true;
    },
  };
}

export const posShortcuts = createShortcutRegistry();

let installed = false;

/** Installs the single window listener. Safe to call more than once. */
export function installPosShortcutListener(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  window.addEventListener(
    "keydown",
    (e) => {
      if (!isF10(e)) return;
      e.preventDefault();
      // A held key repeats; one press is one checkout.
      if (e.repeat) return;
      posShortcuts.dispatch(e);
    },
    { capture: true },
  );
  window.addEventListener(
    "keyup",
    (e) => {
      if (isF10(e)) e.preventDefault();
    },
    { capture: true },
  );
}
