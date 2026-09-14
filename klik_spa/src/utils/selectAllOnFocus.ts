import type { FocusEvent, MouseEvent } from "react";

/**
 * Spread onto an amount input so focusing it selects the whole value: the cashier types
 * 1500 over a prefilled 1459 instead of editing digits.
 *
 * Selecting in onFocus alone does not survive a click - the mouseup that follows puts the
 * caret back where the pointer landed. Swallow that one mouseup, and only that one, so a
 * later click inside an already-focused field still places the caret normally.
 */
const justFocused = new WeakSet<HTMLInputElement>();

export const selectAllOnFocus = {
  onFocus: (event: FocusEvent<HTMLInputElement>) => {
    event.currentTarget.select();
    justFocused.add(event.currentTarget);
  },
  onMouseUp: (event: MouseEvent<HTMLInputElement>) => {
    if (justFocused.has(event.currentTarget)) {
      event.preventDefault();
      justFocused.delete(event.currentTarget);
    }
  },
};
