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
  // The format's CSS has a <style> of its own: Frappe puts a Print Style's @import first,
  // and CSS ignores an @import that follows any other rule.
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<base target="_blank">
<style>
html, body { margin: 0; background: #fff; color: #000; }
/* The frame is as tall as the page, so it never scrolls up and down. */
html { overflow-y: hidden; }
/* Holds the format's margins inside the body, so the body's height is the frame's. */
body { display: flow-root; }
</style>
<style>${safeStyle}</style>
</head>
<body data-print-preview>
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

/** How tall the frame must be to show all of its page.
 *
 * The body, not the root: the root's scrollHeight is never less than the frame, so a shorter
 * invoice loaded into a taller frame would keep the old height. The body's scrollHeight
 * counts a format that sets `html, body { height: 100% }`, whose body is the frame's height -
 * 0px at first. A format wider than a narrow till panel scrolls sideways, and that scrollbar
 * takes its height from the page, so it is added back.
 */
export function previewFrameHeight(page: Document | null | undefined): number {
  const body = page?.body;
  if (!body) return 0;
  const view = page.defaultView;
  const sidewaysScrollbar = view ? Math.max(0, view.innerHeight - page.documentElement.clientHeight) : 0;
  return Math.ceil(Math.max(body.getBoundingClientRect().height, body.scrollHeight)) + sidewaysScrollbar;
}

/** The frame's preview page, once its markup has been read.
 *
 * The frame's `load` waits for every image - the letterhead - so a frame sized on `load` sat
 * empty until then. The page can be sized as soon as it is parsed; images that load later
 * grow its body. Not before it is parsed: the footer to unpin may not be in it yet. Not the
 * blank page every frame starts on, which has no marker. The preview gives each invoice's
 * page a frame of its own, so a marked page is always the one being waited for. A fixed
 * footer whose rule is in an @import'ed sheet is not fixed yet at this point; load unpins it.
 */
export function parsedPreviewPage(frame: Pick<HTMLIFrameElement, "contentDocument"> | null | undefined): Document | null {
  const page = frame?.contentDocument;
  if (!page || page.readyState === "loading") return null;
  return page.body?.hasAttribute("data-print-preview") ? page : null;
}
