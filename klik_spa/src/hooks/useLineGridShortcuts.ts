import { useEffect, useLayoutEffect, useRef } from "react";
import { useCartStore } from "../stores/cartStore";

interface LineGridShortcuts {
  focusEntry: () => void;
  focusPanel: () => void;
  toggleHelp: () => void;
}

/**
 * The grid till's page keys, standing in for MenuGrid's (which isn't mounted in grid mode):
 * F2 customer, F3 entry row, F8 side panel, `?` help (outside inputs). F10 stays with posShortcuts
 * and F4 with CustomerSearchSection, which ignores keys typed in inputs - but the grid's cursor is
 * always in one, so F4 from a grid cell is handled here, under the same customer rule.
 * Backspace is plain editing here.
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
      } else if (e.key === "F4" && target.closest("[data-col]") && useCartStore.getState().selectedCustomer) {
        e.preventDefault();
        useCartStore.getState().setAdditionalInfoOpen(true);
      } else if (e.key === "?" && !inInput) {
        e.preventDefault();
        latest.current.toggleHelp();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [active]);
}
