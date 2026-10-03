import { useState, useEffect, useRef, useMemo, useCallback, type SyntheticEvent } from "react";
import { getPrintFormatHTML } from "./getPrintHTML.js";
import { buildPrintPreviewDocument, unpinFixedElements } from "./printPreviewDocument";
import { usePOSProfileStore } from "../stores/posProfileStore.js";

type PrintPreviewProps = {
  invoice: {
    pos_profile: string;
    name: string;
    [key: string]: unknown;
  };
};

export default function PrintPreview({ invoice }: PrintPreviewProps) {
  const [html, setHtml] = useState("");
  const [style, setStyle] = useState("");
  const [loading, setLoading] = useState(true);
  const lastLoadedKeyRef = useRef<string>("");

  const { posDetails, isLoading: posLoading } = usePOSProfileStore();
  const invoiceName = typeof invoice?.name === "string" ? invoice.name : "";
  const posProfile = typeof invoice?.pos_profile === "string" ? invoice.pos_profile : "";
  const printFormat = typeof posDetails?.print_format === "string" ? posDetails.print_format : "";

  useEffect(() => {
    let isCancelled = false;

    const fetchPrintHTML = async () => {
      // Wait until posDetails is loaded
      if (posLoading || !posDetails) return;

      const requestKey = `${invoiceName}::${posProfile}::${printFormat}`;
      if (requestKey === lastLoadedKeyRef.current && html) {
        return;
      }

      setLoading(true);
      try {
        const invoiceForAPI: { doctype: string; name: string; [key: string]: unknown } = {
          ...invoice,
          doctype: "Sales Invoice",
          name: invoiceName,
        };

        const { html: previewHtml, style: previewStyle } = await getPrintFormatHTML(
          invoiceForAPI,
          printFormat
        );

        if (isCancelled) return;

        setHtml(previewHtml);
        setStyle(previewStyle);
        lastLoadedKeyRef.current = requestKey;
      } catch (err) {
        if (!isCancelled) {
          console.error("Error loading print format:", err);
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    };

    fetchPrintHTML();

    return () => {
      isCancelled = true;
    };
  }, [invoice, invoiceName, posProfile, posLoading, posDetails, printFormat, html]);

  const srcDoc = useMemo(() => buildPrintPreviewDocument(html, style), [html, style]);
  const [frameHeight, setFrameHeight] = useState(0);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // The format is shown in its own document so its CSS and fixed footer stay inside the
  // preview. The frame is as tall as its page; the container scrolls it as before.
  const fitToContent = useCallback((event: SyntheticEvent<HTMLIFrameElement>) => {
    const frameDocument = event.currentTarget.contentDocument;
    const page = frameDocument?.body;
    if (!page) return;
    unpinFixedElements(frameDocument);
    // The body, not the root: the root's scrollHeight is never less than the frame, so a
    // shorter invoice loaded into a taller frame would keep the old height.
    const fit = () => setFrameHeight(Math.ceil(page.getBoundingClientRect().height));
    fit();
    resizeObserverRef.current?.disconnect();
    if (typeof ResizeObserver !== "undefined") {
      resizeObserverRef.current = new ResizeObserver(fit);
      resizeObserverRef.current.observe(page);
    }
  }, []);

  useEffect(() => () => resizeObserverRef.current?.disconnect(), []);

  if (loading) return <p>Loading Print Preview...</p>;

  return (
    <div className="print-preview-container p-4 relative bg-white dark:bg-gray-800 shadow overflow-auto max-h-[90vh]">
      <iframe
        className="print-preview-content block w-full border-0 bg-white"
        title="Print preview"
        // No allow-scripts: a format's markup is shown, never run. allow-same-origin lets
        // this page measure the frame and unpin its fixed footer.
        sandbox="allow-same-origin allow-popups"
        srcDoc={srcDoc}
        onLoad={fitToContent}
        style={{ height: frameHeight }}
      />
    </div>
  );
}
