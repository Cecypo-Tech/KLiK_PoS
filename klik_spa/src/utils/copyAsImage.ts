/**
 * PowerPack's Copy as Image for a held order: a PNG of the order's print (default print
 * format), rendered by cecypo_powerpack.copy_as_image.get_print_image, put on the clipboard.
 * Same handling as PowerPack's desk button (public/js/copy_as_image.js).
 */

export const PRINT_IMAGE_METHOD = "/api/method/cecypo_powerpack.copy_as_image.get_print_image";

export interface CopyImageDeps {
  fetchImpl?: typeof fetch;
  notify: (message: string, level: "info" | "success" | "warning" | "error") => void;
  csrfToken?: string | null;
}

let busy = false;

export async function fetchPrintImage(
  doctype: string,
  name: string,
  { fetchImpl = fetch, csrfToken }: Pick<CopyImageDeps, "fetchImpl" | "csrfToken"> = {}
): Promise<Blob> {
  const params = new URLSearchParams({ doctype, name });
  const response = await fetchImpl(`${PRINT_IMAGE_METHOD}?${params}`, {
    credentials: "same-origin",
    headers: csrfToken ? { "X-Frappe-CSRF-Token": csrfToken } : {},
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return new Blob([await response.arrayBuffer()], { type: "image/png" });
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const messages = (JSON.parse(body._server_messages || "[]") as string[]).map(
      (m) => (JSON.parse(m) as { message: string }).message
    );
    if (messages.length) return messages.join(" ").replace(/<[^>]*>/g, "");
    if (body.exc_type) return String(body.exc_type);
  } catch {
    // Not a frappe error body.
  }
  return "Failed to create the image";
}

function download(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${name.replace(/[ /]/g, "-")}.png`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/**
 * Must be called from the click handler: Safari lets a page write to the clipboard only
 * during the click, so the ClipboardItem gets the pending render straight away.
 */
export function copyPrintImage(doctype: string, name: string, deps: CopyImageDeps): Promise<void> {
  // A render takes a few seconds and holds a server worker; ignore repeat clicks.
  if (busy) return Promise.resolve();
  busy = true;
  deps.notify("Preparing image…", "info");

  const png = fetchPrintImage(doctype, name, deps);
  let written: Promise<void>;
  try {
    written = navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
  } catch (e) {
    written = Promise.reject(e);
  }

  return written
    .then(() => deps.notify("Image copied", "success"))
    .catch(() =>
      // The clipboard refused the image (older browser, or the tab lost focus while it
      // rendered) - download it; or the render failed - say why.
      png.then(
        (blob) => {
          download(blob, name);
          deps.notify("Could not copy the image, so it was downloaded instead", "warning");
        },
        (e: Error) => deps.notify(e.message || "Failed to create the image", "error")
      )
    )
    .finally(() => {
      busy = false;
    });
}
