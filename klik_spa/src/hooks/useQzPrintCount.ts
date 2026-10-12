import { useCallback, useEffect, useState } from "react";
import { qzPrintCount } from "../utils/qzPrint";

// A reprint only queues the job; it counts once the station agent marks it
// Printed, a few seconds later.
const RECOUNT_AFTER_MS = 8000;

/**
 * The QZ print count for an invoice, and a way to recount after a reprint.
 * Fetches nothing (count 0) while QZ printing is off or there is no invoice.
 */
export function useQzPrintCount(invoiceName: string, enabled: boolean) {
  const [count, setCount] = useState(0);
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (!enabled || !invoiceName) {
      setCount(0);
      return;
    }
    // A reply for the previous invoice must not land on this one.
    let current = true;
    void qzPrintCount(invoiceName).then((n) => {
      if (current) setCount(n);
    });
    return () => {
      current = false;
    };
  }, [invoiceName, enabled, round]);

  const recountSoon = useCallback(() => {
    window.setTimeout(() => setRound((r) => r + 1), RECOUNT_AFTER_MS);
  }, []);

  return { count, recountSoon };
}
