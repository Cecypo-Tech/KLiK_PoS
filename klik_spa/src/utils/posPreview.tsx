import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { getPrintFormatHTML } from "./getPrintHTML.js";
import { buildPrintPreviewDocument, parsedPreviewPage, previewFrameHeight, unpinFixedElements } from "./printPreviewDocument";
import { drawPreviewBarcodes } from "./previewBarcodes";
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
  const frameRef = useRef<HTMLIFrameElement>(null);
  const waitForPageRef = useRef(0);

  // The format is shown in its own document so its CSS and fixed footer stay inside the
  // preview. The frame is as tall as its page; the container scrolls it as before.
  const fitToPage = useCallback((frameDocument: Document) => {
    const page = frameDocument.body;
    if (!page) return;
    drawPreviewBarcodes(frameDocument);
    unpinFixedElements(frameDocument);
    const fit = () => setFrameHeight(previewFrameHeight(frameDocument));
    fit();
    resizeObserverRef.current?.disconnect();
    if (typeof ResizeObserver !== "undefined") {
      resizeObserverRef.current = new ResizeObserver(fit);
      resizeObserverRef.current.observe(page);
    }
  }, []);

  // Size the page once it is parsed rather than on load, which waits for the letterhead and
  // every other image; the observer grows the frame as they arrive.
  useEffect(() => {
    const frame = frameRef.current;
    if (loading || !frame) return;
    const waitForPage = () => {
      const page = parsedPreviewPage(frame);
      if (page) fitToPage(page);
      else waitForPageRef.current = requestAnimationFrame(waitForPage);
    };
    waitForPage();
    return () => cancelAnimationFrame(waitForPageRef.current);
  }, [srcDoc, loading, fitToPage]);

  useEffect(() => () => resizeObserverRef.current?.disconnect(), []);

  if (loading) return <p>Loading Print Preview...</p>;

  return (
    <div className="print-preview-container p-4 relative bg-white dark:bg-gray-800 shadow overflow-auto max-h-[90vh]">
      <iframe
        className="print-preview-content block w-full border-0 bg-white"
        title="Print preview"
        // No allow-scripts: a format's markup is shown, never run. allow-same-origin lets
        // this page measure the frame and unpin its fixed footer; a link opens a normal tab.
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        // A frame per page: the wait above then never mistakes the last invoice's page,
        // still in a reused frame, for the next one's.
        key={srcDoc}
        ref={frameRef}
        srcDoc={srcDoc}
        // Again on load, once images and imported sheets are in; a wait still running ends.
        onLoad={(event) => {
          cancelAnimationFrame(waitForPageRef.current);
          const page = event.currentTarget.contentDocument;
          if (page) fitToPage(page);
        }}
        style={{ height: frameHeight }}
      />
    </div>
  );
}
