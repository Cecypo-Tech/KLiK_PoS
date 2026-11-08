import { useEffect, useLayoutEffect, useRef } from "react";

interface LineGridShortcuts {
  focusEntry: () => void;
  focusPanel: () => void;
  toggleHelp: () => void;
}

/**
 * The grid till's page keys, standing in for MenuGrid's (which isn't mounted in grid mode):
 * F2 customer, F3 entry row, F8 side panel, `?` help (outside inputs). F4 and F10 stay with
 * CustomerSearchSection / posShortcuts; Backspace is plain editing here.
 */
export function useLineGridShortcuts(handlers: LineGridShortcuts, active: boolean): void {
  const latest = useRef(handlers);
  useLayoutEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
      if (e.key === "F2") {
        e.preventDefault();
        document.getElementById("pos-customer-btn")?.click();
      } else if (e.key === "F3") {
        e.preventDefault();
        latest.current.focusEntry();
      } else if (e.key === "F8") {
        e.preventDefault();
        latest.current.focusPanel();
      } else if (e.key === "?" && !inInput) {
        e.preventDefault();
        latest.current.toggleHelp();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [active]);
}
