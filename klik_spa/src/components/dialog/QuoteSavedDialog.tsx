import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import { Loader2, MailPlus, MessageCirclePlus } from "lucide-react";
import DocShareButtons from "../DocShareButtons";
import { sendWhatsAppMessage } from "../../services/useSharing";
import { getQuoteEmails, sendQuoteEmail } from "../../services/quotation";

interface QuoteSavedDialogProps {
  /** "Quote saved" after saving; Invoice History reuses it to send a quote from the list. */
  title?: string;
  quoteName: string;
  customerName: string;
  /** Prefills the WhatsApp number: the walk-in's or the customer's phone. */
  phone: string;
  posDetails: Record<string, unknown> | null;
  onDone: () => void;
}

// ponytail: plain number + send, not the checkout's SharingInterface (needs ~30 checkout-only
// props); the server writes the message. Reuse SharingInterface if templates are wanted here.
export default function QuoteSavedDialog({ title = "Quote saved", quoteName, customerName, phone, posDetails, onDone }: QuoteSavedDialogProps) {
  const [mobile, setMobile] = useState(phone);
  const [sending, setSending] = useState(false);
  const [emails, setEmails] = useState("");
  const [emailing, setEmailing] = useState(false);

  // Prefill from the quote's contact and customer; never overwrite what the cashier typed.
  useEffect(() => {
    let live = true;
    void getQuoteEmails(quoteName).then((found) => {
      if (live && found.length) setEmails((typed) => typed || found.join(", "));
    });
    return () => { live = false; };
  }, [quoteName]);

  const sendEmail = async () => {
    if (!emails.trim()) {
      toast.error("Enter an email address");
      return;
    }
    setEmailing(true);
    try {
      await sendQuoteEmail(quoteName, emails);
      toast.success(`${quoteName} emailed`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to send the email");
    } finally {
      setEmailing(false);
    }
  };

  const sendWhatsApp = async () => {
    if (!mobile.trim()) {
      toast.error("Enter a mobile number");
      return;
    }
    setSending(true);
    try {
      await sendWhatsAppMessage({
        mobile_no: mobile.trim(),
        customer_name: customerName,
        invoice_data: quoteName,
        doctype: "Quotation",
      });
      toast.success(`${quoteName} sent on WhatsApp`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to send WhatsApp message");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-gray-950/45 px-4">
      <div
        role="dialog"
        aria-labelledby="quote-saved-title"
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-700 space-y-4"
      >
        <div>
          <h2 id="quote-saved-title" className="text-xl font-semibold text-gray-900 dark:text-white">
            {title}
          </h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            {quoteName}{customerName ? ` for ${customerName}` : ""}
          </p>
        </div>

        <div className="flex items-center justify-center gap-1 rounded-xl border border-gray-200 py-1 dark:border-gray-700">
          <DocShareButtons doctype="Quotation" name={quoteName} size="md" posDetails={posDetails} />
        </div>

        <div className="flex gap-2">
          <input
            type="tel"
            aria-label="WhatsApp number"
            placeholder="WhatsApp number"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            className="min-w-0 flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
          <button
            type="button"
            onClick={() => void sendWhatsApp()}
            disabled={sending}
            className="flex items-center gap-2 rounded-xl bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageCirclePlus className="h-4 w-4" />}
            WhatsApp
          </button>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            inputMode="email"
            aria-label="Email addresses"
            placeholder="Email (comma-separate several)"
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void sendEmail(); }}
            className="min-w-0 flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
          <button
            type="button"
            onClick={() => void sendEmail()}
            disabled={emailing}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {emailing ? <Loader2 className="h-4 w-4 animate-spin" /> : <MailPlus className="h-4 w-4" />}
            Email
          </button>
        </div>

        <button
          type="button"
          autoFocus
          onClick={onDone}
          className="w-full rounded-xl bg-beveren-600 py-2 text-sm font-semibold text-white hover:bg-beveren-700"
        >
          Done
        </button>
      </div>
    </div>
  );
}
