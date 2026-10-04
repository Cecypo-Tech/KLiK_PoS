import { useEffect } from "react";
import { toast } from "react-toastify";
import { formatQueueFailure, QUEUE_FAILURE_EVENT, type QueueFailureEvent } from "../utils/queueFailure";

export { QUEUE_FAILURE_EVENT };

interface FrappeRealtimeClient {
  on?: (event: string, handler: (data: QueueFailureEvent) => void) => void;
  off?: (event: string, handler: (data: QueueFailureEvent) => void) => void;
}

/**
 * Surface background invoice-submission failures at the till.
 *
 * Mounted once at the app root rather than in the checkout dialog: the dialog has already
 * closed by the time a queued submit fails, and the cashier may have moved on to the next
 * sale. The toast does not auto-dismiss - an unposted sale is not something to notice or
 * miss within three seconds.
 */
export function useQueueFailureAlerts() {
  useEffect(() => {
    const handler = (data: QueueFailureEvent) => {
      toast.error(formatQueueFailure(data), { autoClose: false });
    };
    // The till page has no realtime client: the checkout's own status poll announces a
    // failure as a window event instead (see watchQueuedCheckout).
    const onWindowEvent = (event: Event) => handler((event as CustomEvent<QueueFailureEvent>).detail);
    window.addEventListener(QUEUE_FAILURE_EVENT, onWindowEvent);

    const realtime = (window as typeof window & { frappe?: { realtime?: FrappeRealtimeClient } })
      ?.frappe?.realtime;
    realtime?.on?.(QUEUE_FAILURE_EVENT, handler);
    return () => {
      window.removeEventListener(QUEUE_FAILURE_EVENT, onWindowEvent);
      realtime?.off?.(QUEUE_FAILURE_EVENT, handler);
    };
  }, []);
}
