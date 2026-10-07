/** A keydown listener that swallows one key. Added on window in the capture phase it runs
 * before the window's ordinary listeners - the POS's own shortcuts - so they never see it. */
export const blockKey =
  (key: string) => (event: Pick<KeyboardEvent, "key" | "preventDefault" | "stopImmediatePropagation">) => {
    if (event.key !== key) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  };
