/** The page an <iframe srcdoc> shows a print format on.
 *
 * A print format is written for its own page: its CSS is global (Frappe's print stylesheet
 * styles `.table`, `table td div`, `thead` ...) and a repeating footer is `position: fixed`.
 * Put into the app's DOM, that CSS restyled klik and the footer was pinned to the bottom of
 * the klik screen. Frappe's own print view shows formats in an iframe for the same reason.
 */
export function buildPrintPreviewDocument(html: string | undefined, style: string | undefined): string {
  // A "</style>" inside the CSS would end the style element and turn the rest into markup.
  const safeStyle = (style || "").replace(/<\/style/gi, "<\\/style");
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<base target="_blank">
<style>
html, body { margin: 0; background: #fff; color: #000; }
/* Holds the format's margins inside the body, so the body's height is the frame's. */
body { display: flow-root; }
${safeStyle}
</style>
</head>
<body>
${html || ""}
</body>
</html>`;
}

/** Put the format's `position: fixed` elements back where it wrote them.
 *
 * On paper a fixed element repeats on every page - a format's running footer of totals, say.
 * The preview is one long page, so the footer sat over the lines at the bottom of the frame.
 * In the flow it follows the lines, as on a one-page print.
 */
export function unpinFixedElements(page: Document | null | undefined): void {
  const view = page?.defaultView;
  if (!page?.body || !view) return;
  for (const element of Array.from(page.body.querySelectorAll<HTMLElement>("*"))) {
    if (view.getComputedStyle(element).position === "fixed") {
      element.style.setProperty("position", "static", "important");
    }
  }
}
