const CONTROLS = "input, button, textarea, select, a, label";

/**
 * True when a click on a clickable row started inside one of the row's own controls.
 *
 * The row toggles on click, but its amount input, reference input and buttons handle their
 * own clicks: letting those bubble would turn a row off as the cashier clicks in to type an
 * amount, and would toggle twice when the circle button is pressed. Only controls inside
 * the row count - one wrapping the row is not the row's business.
 */
export function clickCameFromControl(target: EventTarget | null, row: Element): boolean {
  const el = target as Element | null;
  if (!el || typeof el.closest !== "function") return false;
  const control = el.closest(CONTROLS);
  return !!control && row.contains(control);
}

/**
 * True for a click the cashier did not mean as a toggle: the second (or third) click of a
 * double-click, which would flip the row straight back, and the click that ends a drag to
 * select text such as the method name.
 */
export function isIncidentalClick(detail: number, selectedText: string): boolean {
  return detail > 1 || selectedText.length > 0;
}
