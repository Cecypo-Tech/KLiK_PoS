import { useEffect, useLayoutEffect, useRef } from "react";
import { useCartStore } from "../stores/cartStore";

interface LineGridShortcuts {
  focusEntry: () => void;
  focusPanel: () => void;
  toggleHelp: () => void;
}

/** A dialog or full-screen overlay: QuickEntryDialog (role=dialog), SalespersonAuthModal and the
 * camera scanner (fixed inset-0 only), the help panel. */
export const OVERLAY_SELECTOR = '[role="dialog"], [aria-modal="true"], .fixed.inset-0';

export const overlayOpen = (root: Pick<Document, "querySelector"> = document): boolean =>
  !!root.querySelector(OVERLAY_SELECTOR);

/**
 * The grid till's page keys, standing in for MenuGrid's (header-only in grid mode, with its key
 * handler off): F2 customer, F3 entry row, F8 side panel, `?` help (outside inputs).
 * None fire while a dialog or overlay is open: they would act behind it (the help panel closes itself on `?`). F10 stays with posShortcuts
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
      if (overlayOpen()) return;
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
