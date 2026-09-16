import { useEffect, useLayoutEffect, useRef } from "react";
import { installPosShortcutListener, posShortcuts, type ShortcutLayer } from "../utils/posShortcuts";

/**
 * Registers F10 / Shift+F10 handlers while `active`. The handlers may change on every
 * render; the layer always calls the latest ones.
 */
export function usePosShortcutLayer(handlers: ShortcutLayer, active = true): void {
  const latest = useRef(handlers);
  // After commit, so a render React discards never leaves its handlers behind.
  useLayoutEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    installPosShortcutListener();
    if (!active) return;
    return posShortcuts.push({
      f10: () => latest.current.f10?.(),
      shiftF10: () => latest.current.shiftF10?.(),
    });
  }, [active]);
}
