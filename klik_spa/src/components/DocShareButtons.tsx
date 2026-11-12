import { useEffect, useRef, useState } from "react";
import { toast } from "react-toastify";
import { Copy, Image as ImageIcon, Printer } from "lucide-react";
import HeldOrderQzButton from "./HeldOrderQzButton";
import { handlePrintInvoice } from "../utils/printHandler";
import { copyPrintImage } from "../utils/copyAsImage";
import { deferredClipboardText, formatSystemDate, runCopyAsMessage } from "../utils/copyAsMessage";
import { callMethod, getHeldOrderShareDoc, getHeldOrderShareTools, type HeldOrderShareTools } from "../services/salesOrder";
import { formatCurrencyWithSymbol } from "../utils/currency";
import { getCSRFToken } from "../utils/csrf";
import { useUserInfo } from "../hooks/useUserInfo";

const NONE: HeldOrderShareTools = { copy_message_script: null, copy_image: false, date_format: null };
// One fetch per doctype for the page's life, not one per row.
const toolsByDoctype = new Map<string, Promise<HeldOrderShareTools>>();
const loadTools = (doctype: string) => {
  if (!toolsByDoctype.has(doctype)) toolsByDoctype.set(doctype, getHeldOrderShareTools(doctype).catch(() => NONE));
  return toolsByDoctype.get(doctype)!;
};

interface Props {
  /** "Sales Order" for a held order, "Quotation" for a quote, "Sales Invoice" for an invoice. */
  doctype: string;
  name: string;
  size: "sm" | "md";
  posDetails: Record<string, unknown> | null | undefined;
  /** Set when the till blocks printing this document: the print-based buttons show, disabled, with it as tooltip. */
  blockedTitle?: string;
  /** Only Copy as message and Copy as image: for a screen that has its own Print and QZ. */
  copyOnly?: boolean;
}

/** Print, QZ, Copy as message and Copy as image: each only when the site and till have it. */
export default function DocShareButtons({ doctype, name, size, posDetails, blockedTitle, copyOnly }: Props) {
  const [tools, setTools] = useState<HeldOrderShareTools>(NONE);
  const copying = useRef(false);
  const { userInfo } = useUserInfo();

  useEffect(() => {
    let live = true;
    void loadTools(doctype).then((t) => live && setTools(t));
    return () => {
      live = false;
    };
  }, [doctype]);

  const copyMessage = async () => {
    if (!tools.copy_message_script || copying.current) return;
    copying.current = true;
    // Taken during the click: Safari refuses a clipboard write that comes after the fetches.
    const clipboard = deferredClipboardText();
    try {
      const { doc, currency_symbol } = await getHeldOrderShareDoc(name, doctype);
      await runCopyAsMessage(tools.copy_message_script, doc, {
        call: callMethod,
        alert: (message, ok) => (ok ? toast.success(message) : toast.error(message)),
        formatCurrency: (value) => formatCurrencyWithSymbol(value, currency_symbol),
        formatDate: (date) => formatSystemDate(date, tools.date_format),
        writeText: clipboard.writeText,
        user: userInfo?.user,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not copy the message");
    } finally {
      clipboard.done();
      copying.current = false;
    }
  };

  const copyImage = () =>
    void copyPrintImage(doctype, name, {
      csrfToken: getCSRFToken(),
      notify: (message, level) => toast[level](message, level === "info" ? { autoClose: 3000 } : undefined),
    });

  const qzEnabled = [1, "1", true].includes(posDetails?.custom_enable_qz_print as 1 | "1" | true);
  const icon = size === "sm" ? "w-4 h-4" : "w-5 h-5";
  // Icons only, so on a touch screen each needs a finger-sized target.
  const button = (size === "sm" ? "p-1" : "p-2.5") + " rounded text-gray-600 hover:text-beveren-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent";

  return (
    <>
      {!copyOnly && (
        <button type="button" title={blockedTitle ?? "Print"} aria-label="Print" className={button}
          disabled={!!blockedTitle}
          onClick={() => handlePrintInvoice({ name, pos_profile: "" }, { doctype, posDetails })}>
          <Printer className={icon} />
        </button>
      )}
      {!copyOnly && qzEnabled && (
        <HeldOrderQzButton orderId={name} doctype={doctype} className={button} iconSize={size === "sm" ? 16 : 20}
          blockedTitle={blockedTitle} />
      )}
      {tools.copy_message_script && (
        <button type="button" title="Copy as message" aria-label="Copy as message" className={button}
          onClick={() => void copyMessage()}>
          <Copy className={icon} />
        </button>
      )}
      {tools.copy_image && (
        <button type="button" title={blockedTitle ?? "Copy as image"} aria-label="Copy as image" className={button}
          disabled={!!blockedTitle}
          onClick={copyImage}>
          <ImageIcon className={icon} />
        </button>
      )}
    </>
  );
}
